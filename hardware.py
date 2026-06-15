"""
hardware.py
───────────────────────────────────────────────────────────────────────
Thin wrappers around each instrument.
All blocking calls; thread-safety is handled by the caller (scan_worker).
"""

import time
import logging
import serial
import numpy as np
import pyvisa

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  VISA backend loader
# ══════════════════════════════════════════════════════════════════════
def _get_resource_manager() -> pyvisa.ResourceManager:
    """
    Use NI-VISA (system install). No driver modifications needed. User needs to install NI drivers: https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html
    """
    try:
        rm = pyvisa.ResourceManager()   # picks up NI-VISA automatically
        resources = rm.list_resources()
        log.debug("NI-VISA resources: %s", resources)

        usb_resources = [r for r in resources if r.startswith("USB")]
        if usb_resources:
            log.info("NI-VISA found USB devices: %s", usb_resources)
        else:
            log.warning(
                "NI-VISA running but no USB devices found yet. "
                "Is the Keithley powered on and plugged in?")

        return rm

    except Exception as e:
        raise RuntimeError(
            f"NI-VISA not found or failed: {e}\n\n"
            "Install NI-VISA from:\n"
            "https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html"
        )

# ══════════════════════════════════════════════════════════════════════
#  Arduino / Motor Controller
# ══════════════════════════════════════════════════════════════════════
class MotorController:
    """Wraps the Arduino serial protocol."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 10.0,
                 steps_per_degree: float = 88.89,
                 max_speed: int = 2000,
                 m1_invert: bool = False,
                 m2_invert: bool = False):
        self.steps_per_degree = steps_per_degree
        self.max_speed = max_speed
        self.m1_invert = m1_invert
        self.m2_invert = m2_invert
        self._ser = None
        self._port = port
        self._baud = baud
        self._timeout = timeout

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._ser = serial.Serial(self._port, self._baud,
                                  timeout=self._timeout)
        time.sleep(2.0)          # Arduino resets on connect
        resp = self._ser.readline().decode().strip()
        if resp != "READY":
            raise ConnectionError(
                f"Arduino did not say READY, got: {resp!r}\n"
                "Check the COM port in config.yaml")
        self._send_speed(self.max_speed)
        log.info("Motor controller connected on %s", self._port)

    def disconnect(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            log.info("Motor controller disconnected")

    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── Low-level ─────────────────────────────────────────────────────
    def _cmd(self, msg: str) -> str:
        self._ser.write((msg + "\n").encode())
        resp = self._ser.readline().decode().strip()
        return resp

    def _send_speed(self, steps_per_sec: int):
        r = self._cmd(f"SPEED {steps_per_sec}")
        if r != "OK":
            raise RuntimeError(f"SPEED command failed: {r}")

    # ── Public API ────────────────────────────────────────────────────
    def move_steps(self, motor: int, steps: int, direction: int):
        """Move motor (1 or 2) by raw steps in direction (0 or 1)."""
        if not self.is_connected():
            raise RuntimeError("Motor controller not connected")
        if (motor == 1 and self.m1_invert) or (motor == 2 and self.m2_invert):
            direction = 1 - direction
        r = self._cmd(f"MOVE {motor} {abs(steps)} {direction}")
        if r != "OK":
            raise RuntimeError(f"MOVE failed: {r}")

    def move_degrees(self, motor: int, degrees: float):
        """Move motor by signed degrees (negative = reverse)."""
        steps = int(round(abs(degrees) * self.steps_per_degree))
        direction = 1 if degrees >= 0 else 0
        self.move_steps(motor, steps, direction)

    def stop(self):
        self._cmd("STOP")

    def zero(self):
        r = self._cmd("ZERO")
        if r != "OK":
            raise RuntimeError(f"ZERO failed: {r}")

    def home(self):
        r = self._cmd("HOME")
        if r != "OK":
            raise RuntimeError(f"HOME failed: {r}")

    def get_position(self) -> tuple:
        """Returns (pos1_steps, pos2_steps)."""
        resp = self._cmd("STATUS")   # "POS <p1> <p2>"
        parts = resp.split()
        return int(parts[1]), int(parts[2])

    def ping(self) -> bool:
        try:
            return self._cmd("PING") == "PONG"
        except Exception:
            return False

    def set_speed(self, steps_per_sec: int):
        self._send_speed(steps_per_sec)


# ══════════════════════════════════════════════════════════════════════
#  OceanOptics Spectrometer
# ══════════════════════════════════════════════════════════════════════
class Spectrometer:
    """Wraps seabreeze for an OceanOptics device."""

    def __init__(self,
                 integration_time_ms: float = 100.0,
                 scans_to_average: int = 3,
                 boxcar_width: int = 2,
                 wl_min: float = 200.0,
                 wl_max: float = 1100.0):
        self._spec = None
        self.integration_time_ms = integration_time_ms
        self.scans_to_average = scans_to_average
        self.boxcar_width = boxcar_width
        self.wl_min = wl_min
        self.wl_max = wl_max
        self._dark = None

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        import seabreeze.spectrometers as sb
        devices = sb.list_devices()
        if not devices:
            raise RuntimeError(
                "No OceanOptics spectrometer found.\n"
                "Check USB connection and seabreeze install.")
        self._spec = sb.Spectrometer(devices[0])
        self._spec.integration_time_micros(
            int(self.integration_time_ms * 1000))
        log.info("Spectrometer connected: %s", self._spec.model)

    def disconnect(self):
        if self._spec:
            self._spec.close()
            self._spec = None
            log.info("Spectrometer disconnected")

    def is_connected(self) -> bool:
        return self._spec is not None

    # ── Settings ──────────────────────────────────────────────────────
    def set_integration_time(self, ms: float):
        self.integration_time_ms = ms
        if self._spec:
            self._spec.integration_time_micros(int(ms * 1000))

    def set_scans_to_average(self, n: int):
        self.scans_to_average = max(1, n)

    def set_boxcar_width(self, w: int):
        self.boxcar_width = max(0, w)

    # ── Dark ──────────────────────────────────────────────────────────
    def collect_dark(self):
        """Store a dark spectrum for subtraction."""
        wl, counts = self._acquire_averaged()
        self._dark = counts.copy()
        log.info("Dark spectrum collected (%d pixels)", len(self._dark))

    def clear_dark(self):
        self._dark = None

    # ── Acquisition ───────────────────────────────────────────────────
    def _acquire_averaged(self) -> tuple:
        """Returns (wavelengths, averaged_counts) numpy arrays, cropped."""
        stacks = []
        for _ in range(self.scans_to_average):
            stacks.append(self._spec.intensities())
        counts = np.mean(stacks, axis=0)

        if self.boxcar_width > 0:
            kernel = np.ones(2 * self.boxcar_width + 1)
            kernel /= kernel.sum()
            counts = np.convolve(counts, kernel, mode='same')

        wl = self._spec.wavelengths()
        mask = (wl >= self.wl_min) & (wl <= self.wl_max)
        return wl[mask], counts[mask]

    def acquire(self, subtract_dark: bool = True) -> tuple:
        """
        Returns (wavelengths, raw_counts, corrected_counts).
        corrected_counts == raw_counts if no dark or subtract_dark=False.
        """
        wl, raw = self._acquire_averaged()
        if subtract_dark and self._dark is not None:
            corr = raw - self._dark[:len(raw)]
        else:
            corr = raw.copy()
        return wl, raw, corr

    def has_dark(self) -> bool:
        return self._dark is not None


# ══════════════════════════════════════════════════════════════════════
#  Keithley 2461 Source-Meter
# ══════════════════════════════════════════════════════════════════════
import time
import logging

log = logging.getLogger(__name__)


class SourceMeterError(Exception):
    """Raised when the SourceMeter detects an unsafe or unexpected operating condition."""


class SourceMeter:
    """
    Minimal wrapper for the Keithley 2461.

    After output_on() the instrument is verified to be operating within
    the expected conditions:

    VOLT source mode
        - Measured current must be >= ``current_threshold`` (default 1 µA).
          A value below this suggests an open circuit or broken connection.
        - Measured current must be < ``compliance_fraction`` × current_limit
          (default 95 %).  A value at or above this means the voltage source
          is in compliance (saturating), which usually indicates a short or
          wiring fault.

    CURR source mode
        - Measured voltage must be >= ``voltage_threshold`` (default 1 mV).
          A value below this suggests a short circuit.
        - Measured voltage must be < ``compliance_fraction`` × voltage_limit
          (default 95 %).  A value at or above this means the current source
          is in compliance (voltage saturating), which usually indicates an
          open circuit or broken connection.

    Both checks also read the 2461's own compliance-event bit so that
    hardware-detected compliance is caught even when the measured value
    has not quite reached the software limit yet.
    """

    # ── Construction ──────────────────────────────────────────────────
    def __init__(self,
                 resource: str,
                 source_mode: str = "VOLT",
                 voltage: float = 5.0,
                 current_limit: float = 0.1,
                 settle_ms: float = 200.0,
                 nplc: float = 1.0,
                 # --- verification knobs ---
                 current_threshold: float = 1e-6,
                 voltage_threshold: float = 1e-3,
                 compliance_fraction: float = 0.95,
                 verify_on_output_on: bool = True):
        self._rm   = None
        self._inst = None
        self.resource      = resource
        self.source_mode   = source_mode.upper()
        self.voltage       = voltage
        self.current_limit = current_limit
        self.settle_ms     = settle_ms
        self.nplc          = nplc

        # Verification parameters
        self.current_threshold   = current_threshold
        self.voltage_threshold   = voltage_threshold
        self.compliance_fraction = compliance_fraction
        self.verify_on_output_on = verify_on_output_on

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._rm = _get_resource_manager()
        resolved = self._resolve_resource(self.resource)
        self._inst = self._rm.open_resource(resolved)
        self._inst.timeout = 10_000

        self._inst.write_termination = "\n"
        self._inst.read_termination  = "\n"

        self._write("*RST")
        self._write("*CLS")
        time.sleep(1.0)
        self._check_errors()
        self._configure()
        log.info("SourceMeter connected: %s", resolved)

    # ── Low-level helpers ─────────────────────────────────────────────
    def _write(self, cmd: str):
        self._inst.write(cmd)

    def _query(self, cmd: str) -> str:
        return self._inst.query(cmd).strip()

    def _check_errors(self) -> bool:
        """Drain the 2461 error queue; log and return True if any found."""
        errors = []
        for _ in range(10):
            resp = self._query("SYST:ERR?")
            if resp.startswith("+0") or resp.startswith("0"):
                break
            errors.append(resp)
        if errors:
            for e in errors:
                log.warning("Keithley error: %s", e)
            return True
        return False

    # ── Configuration ─────────────────────────────────────────────────
    def _configure(self):
        """Send configuration commands for the 2461."""
        if self.source_mode == "VOLT":
            self._write(":SOUR:FUNC VOLT")
            self._write(f":SOUR:VOLT:LEV:IMM {self.voltage:.4f}")
            self._write(f":SOUR:VOLT:ILIM {self.current_limit:.4f}")
            self._write(f":SENS:CURR:NPLC {self.nplc:.2f}")
            self._write(':SENS:FUNC "CURR"')
            self._write(":SENS:CURR:RANG:AUTO ON")
            self._write(":OUTP:SMOD HIMP")
        else:  # CURR
            self._write(":SOUR:FUNC CURR")
            self._write(f":SOUR:CURR:LEV:IMM {self.current_limit:.6f}")
            self._write(f":SOUR:CURR:VLIM {self.voltage:.4f}")
            self._write(f":SENS:VOLT:NPLC {self.nplc:.2f}")
            self._write(':SENS:FUNC "VOLT"')
            self._write(":SENS:VOLT:RANG:AUTO ON")
            self._write(":OUTP:SMOD HIMP")

        if self._check_errors():
            log.warning("Errors after _configure() — check settings")

        log.info("SourceMeter configured: mode=%s  V=%.4f  I=%.6f",
                 self.source_mode, self.voltage, self.current_limit)

    def disconnect(self):
        if self._inst:
            self.output_off()
            self._inst.close()
            self._inst = None
            log.info("SourceMeter disconnected")

    def is_connected(self) -> bool:
        return self._inst is not None

    # ── Settings ──────────────────────────────────────────────────────
    def set_voltage(self, v: float):
        self.voltage = v
        if self._inst:
            cmd = (":SOUR:VOLT:LEV:IMM" if self.source_mode == "VOLT"
                   else ":SOUR:CURR:VLIM")
            self._write(f"{cmd} {v:.4f}")
            self._check_errors()

    def set_current_limit(self, a: float):
        self.current_limit = a
        if self._inst:
            cmd = (":SOUR:VOLT:ILIM" if self.source_mode == "VOLT"
                   else ":SOUR:CURR:LEV:IMM")
            self._write(f"{cmd} {a:.6f}")
            self._check_errors()

    def set_source_mode(self, mode: str):
        self.source_mode = mode.upper()
        if self._inst:
            self._configure()

    # ── Output control ────────────────────────────────────────────────
    def output_on(self):
        """
        Enable the output, wait for settling, then run verify_operation()
        if ``verify_on_output_on`` is True.
        """
        if not self._inst:
            raise RuntimeError("SourceMeter not connected")
        self._write(":OUTP ON")
        time.sleep(self.settle_ms / 1000.0)
        self._check_errors()
        if self.verify_on_output_on:
            self.verify_operation()

    def output_off(self):
        if self._inst:
            self._write(":OUTP OFF")

    # ── Verification ──────────────────────────────────────────────────
    def _is_in_compliance_hw(self) -> bool:
        """
        Ask the 2461 hardware whether the source is currently in compliance
        via the Questionable Status Register (bit 1 = CURR compliance for
        VOLT source, bit 0 = VOLT compliance for CURR source).

        Returns True if the instrument itself reports compliance.
        """
        try:
            qsr = int(self._query(":STAT:QUES:COND?"))
            # Bit 1 → over-current (VOLT source hit current limit)
            # Bit 0 → over-voltage (CURR source hit voltage limit)
            if self.source_mode == "VOLT":
                return bool(qsr & 0b10)   # bit 1
            else:
                return bool(qsr & 0b01)   # bit 0
        except Exception as exc:
            log.debug("Could not read Questionable Status Register: %s", exc)
            return False

    def verify_operation(self) -> dict:
        """
        Measure the output and verify two conditions:

        1. **Signal present** – the measured quantity is above a minimum
           threshold, confirming the circuit is complete.
        2. **No compliance / saturation** – the measured quantity is below
           ``compliance_fraction`` × the configured limit *and* the
           instrument's own compliance bit is not set.

        Returns a result dictionary::

            {
                "mode":           "VOLT" | "CURR",
                "measured":       <float>,       # A (VOLT mode) or V (CURR mode)
                "limit":          <float>,        # current_limit or voltage
                "compliance_hw":  <bool>,         # from the status register
                "signal_ok":      <bool>,
                "compliance_ok":  <bool>,
                "ok":             <bool>,         # True only if both checks pass
            }

        Raises
        ------
        SourceMeterError
            If either check fails, so that callers do not silently proceed
            with a bad measurement setup.  The exception message describes
            which check failed.
        """
        measured = self.measure()
        hw_compliance = self._is_in_compliance_hw()

        if self.source_mode == "VOLT":
            limit     = self.current_limit
            threshold = self.current_threshold
            quantity  = "current"
            unit      = "A"
        else:
            limit     = self.voltage
            threshold = self.voltage_threshold
            quantity  = "voltage"
            unit      = "V"

        soft_limit   = self.compliance_fraction * limit
        signal_ok    = abs(measured) >= threshold
        sw_comp_ok   = abs(measured) < soft_limit
        compliance_ok = sw_comp_ok and not hw_compliance

        result = {
            "mode":          self.source_mode,
            "measured":      measured,
            "limit":         limit,
            "compliance_hw": hw_compliance,
            "signal_ok":     signal_ok,
            "compliance_ok": compliance_ok,
            "ok":            signal_ok and compliance_ok,
        }

        # ── Detailed logging ──────────────────────────────────────────
        log.info(
            "Verification [%s mode]: measured %s = %.6g %s  "
            "(threshold=%.3g, soft_limit=%.3g, hw_compliance=%s)",
            self.source_mode, quantity, measured, unit,
            threshold, soft_limit, hw_compliance,
        )

        # ── Raise on failure ──────────────────────────────────────────
        if not signal_ok:
            msg = (
                f"[{self.source_mode} mode] Measured {quantity} "
                f"({measured:.6g} {unit}) is below the minimum expected "
                f"threshold ({threshold:.3g} {unit}).  "
                f"Possible open circuit or disconnected load."
            )
            log.error(msg)
            raise SourceMeterError(msg)

        if not compliance_ok:
            if hw_compliance:
                reason = "hardware compliance bit is set"
            else:
                reason = (
                    f"measured {quantity} ({measured:.6g} {unit}) "
                    f">= {self.compliance_fraction*100:.0f}% of limit "
                    f"({soft_limit:.6g} {unit})"
                )
            msg = (
                f"[{self.source_mode} mode] Source is saturating / in "
                f"compliance: {reason}.  "
                f"Possible short circuit or incorrect limit setting."
            )
            log.error(msg)
            raise SourceMeterError(msg)

        log.info("Verification passed: signal present, no compliance detected.")
        return result

    # ── Measurement ───────────────────────────────────────────────────
    def measure(self) -> float:
        """
        Returns the primary measured quantity:
          - VOLT source → current (A)
          - CURR source → voltage (V)
        """
        cmd  = ":MEAS:CURR?" if self.source_mode == "VOLT" else ":MEAS:VOLT?"
        resp = self._query(cmd)
        return float(resp.split(",")[0].strip())

    def get_output_state(self) -> bool:
        resp = self._query(":OUTP?").strip()
        return resp in ("1", "ON")

    # ── Resource resolver ─────────────────────────────────────────────
    def _resolve_resource(self, resource: str) -> str:
        all_resources = self._rm.list_resources()
        log.debug("All VISA resources found: %s", all_resources)

        if resource in all_resources:
            return resource

        def _normalise(s: str) -> str:
            return s.replace("::0::INSTR", "::INSTR")

        resource_norm = _normalise(resource)
        for addr in all_resources:
            if _normalise(addr) == resource_norm:
                log.info("Config resource %r loosely matched %r", resource, addr)
                return addr

        log.warning("Resource %r not found directly — scanning...", resource)
        for addr in all_resources:
            try:
                inst = self._rm.open_resource(addr)
                inst.timeout = 2000
                idn = inst.query("*IDN?").strip()
                inst.close()
                if "2461" in idn:
                    log.info("Found Keithley 2461 at %r", addr)
                    return addr
            except Exception:
                continue

        raise RuntimeError(
            f"Keithley 2461 not found.\n"
            f"Config has  : {resource!r}\n"
            f"Available   : {list(all_resources)}"
        )