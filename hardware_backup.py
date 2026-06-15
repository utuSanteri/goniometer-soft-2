"""
hardware.py
───────────────────────────────────────────────────────────────────────
Thin wrappers around each instrument.
All blocking calls; thread-safety is handled by the caller (scan_worker).
"""

import time
import logging
import serial
import pyvisa
import pyvisa_py
import libusb_package
import usb
import seabreeze.spectrometers as sb
import numpy as np

log = logging.getLogger(__name__)


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
            raise ConnectionError(f"Arduino did not say READY, got: {resp!r}")
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
        # Apply invert
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
        devices = sb.list_devices()
        if not devices:
            raise RuntimeError("No OceanOptics spectrometer found")
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

        # Boxcar smoothing
        if self.boxcar_width > 0:
            kernel = np.ones(2 * self.boxcar_width + 1)
            kernel /= kernel.sum()
            counts = np.convolve(counts, kernel, mode='same')

        wl = self._spec.wavelengths()

        # Crop
        mask = (wl >= self.wl_min) & (wl <= self.wl_max)
        return wl[mask], counts[mask]

    def acquire(self, subtract_dark: bool = True) -> tuple:
        """
        Returns (wavelengths, raw_counts, corrected_counts).
        corrected_counts == raw_counts if no dark or subtract_dark=False.
        """
        wl, raw = self._acquire_averaged()
        if subtract_dark and self._dark is not None:
            dark_cropped = self._dark
            # re-crop dark to same mask length (they should match)
            corr = raw - dark_cropped[:len(raw)]
        else:
            corr = raw.copy()
        return wl, raw, corr

    def has_dark(self) -> bool:
        return self._dark is not None


# ══════════════════════════════════════════════════════════════════════
#  Keithley 2461 Source-Meter
# ══════════════════════════════════════════════════════════════════════
'''
class SourceMeter:
    """Minimal wrapper for the Keithley 2461."""

    def __init__(self,
                 resource: str,
                 source_mode: str = "VOLT",
                 voltage: float = 5.0,
                 current_limit: float = 0.1,
                 settle_ms: float = 200.0,
                 nplc: float = 1.0):
        self._rm = pyvisa.ResourceManager("@py")  # force pyvisa-py backend
        self._inst = None
        self.resource = resource
        self.source_mode = source_mode.upper()
        self.voltage = voltage
        self.current_limit = current_limit
        self.settle_ms = settle_ms
        self.nplc = nplc

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._inst = self._rm.open_resource(self.resource)
        self._inst.timeout = 10000
        self._inst.write("*RST")
        self._inst.write("*CLS")
        time.sleep(0.5)
        self._configure()
        log.info("SourceMeter connected: %s", self.resource)

    def _configure(self):
        if self.source_mode == "VOLT":
            self._inst.write("SOUR:FUNC VOLT")
            self._inst.write(f"SOUR:VOLT:LEV {self.voltage:.4f}")
            self._inst.write(f"SENS:CURR:PROT {self.current_limit:.4f}")
            self._inst.write(f"SENS:CURR:NPLC {self.nplc}")
            self._inst.write("SENS:FUNC 'CURR'")
        else:  # CURR
            self._inst.write("SOUR:FUNC CURR")
            self._inst.write(f"SOUR:CURR:LEV {self.current_limit:.6f}")
            self._inst.write(f"SOUR:VOLT:PROT {self.voltage:.4f}")
            self._inst.write(f"SENS:VOLT:NPLC {self.nplc}")
            self._inst.write("SENS:FUNC 'VOLT'")

    def disconnect(self):
        if self._inst:
            self.output_off()
            self._inst.close()
            self._inst = None
            log.info("SourceMeter disconnected")

    def is_connected(self) -> bool:
        return self._inst is not None

    # ── Settings (call before output_on) ──────────────────────────────
    def set_voltage(self, v: float):
        self.voltage = v
        if self._inst:
            if self.source_mode == "VOLT":
                self._inst.write(f"SOUR:VOLT:LEV {v:.4f}")
            else:
                self._inst.write(f"SOUR:VOLT:PROT {v:.4f}")

    def set_current_limit(self, a: float):
        self.current_limit = a
        if self._inst:
            if self.source_mode == "VOLT":
                self._inst.write(f"SENS:CURR:PROT {a:.4f}")
            else:
                self._inst.write(f"SOUR:CURR:LEV {a:.6f}")

    def set_source_mode(self, mode: str):
        self.source_mode = mode.upper()
        if self._inst:
            self._configure()

    # ── Output control ────────────────────────────────────────────────
    def output_on(self):
        if not self._inst:
            raise RuntimeError("SourceMeter not connected")
        self._inst.write("OUTP ON")
        time.sleep(self.settle_ms / 1000.0)

    def output_off(self):
        if self._inst:
            self._inst.write("OUTP OFF")

    def measure(self) -> float:
        """Returns measured value (current if VOLT source, voltage if CURR source)."""
        val = self._inst.query("READ?")
        return float(val.strip())

    def get_output_state(self) -> bool:
        resp = self._inst.query("OUTP?").strip()
        return resp == "1"

'''

class SourceMeter:
    """Minimal wrapper for the Keithley 2461."""

    def __init__(self,
                 resource: str,
                 source_mode: str = "VOLT",
                 voltage: float = 5.0,
                 current_limit: float = 0.1,
                 settle_ms: float = 200.0,
                 nplc: float = 1.0):
        self._rm   = None
        self._inst = None
        self.resource      = resource
        self.source_mode   = source_mode.upper()
        self.voltage       = voltage
        self.current_limit = current_limit
        self.settle_ms     = settle_ms
        self.nplc          = nplc

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._rm = _get_resource_manager()
        resolved = self._resolve_resource(self.resource)
        self._inst = self._rm.open_resource(resolved)
        self._inst.timeout = 10000

        # 2461 needs this termination character
        self._inst.write_termination  = "\n"
        self._inst.read_termination   = "\n"

        self._write("*RST")
        self._write("*CLS")
        time.sleep(1.0)           # give 2461 time to reset fully
        self._check_errors()      # clear any reset-time errors
        self._configure()
        log.info("SourceMeter connected: %s", resolved)

    # ── Safe write + error check helpers ─────────────────────────────
    def _write(self, cmd: str):
        """Write a command and immediately check for SCPI errors."""
        self._inst.write(cmd)

    def _query(self, cmd: str) -> str:
        return self._inst.query(cmd).strip()

    def _check_errors(self):
        """
        Drain the 2461 error queue and log anything found.
        Returns True if errors were present.
        """
        errors = []
        for _ in range(10):      # max 10 errors in queue
            resp = self._query("SYST:ERR?")
            # Format: +0,"No error" or -113,"Undefined header"
            if resp.startswith("+0") or resp.startswith("0"):
                break
            errors.append(resp)
        if errors:
            for e in errors:
                log.warning("Keithley error: %s", e)
            return True
        return False

    def _configure(self):
        """Send configuration commands correct for the 2461."""

        if self.source_mode == "VOLT":
            self._write(":SOUR:FUNC VOLT")
            self._write(f":SOUR:VOLT:LEV:IMM {self.voltage:.4f}")
            self._write(f":SOUR:VOLT:ILIM {self.current_limit:.4f}")  # 2461 current limit
            self._write(f":SENS:CURR:NPLC {self.nplc:.2f}")
            self._write(':SENS:FUNC "CURR"')                          # double quotes
            self._write(":SENS:CURR:RANG:AUTO ON")
            self._write(":OUTP:SMOD HIMP")                           # output-off = Hi-Z safe

        else:  # CURR
            self._write(":SOUR:FUNC CURR")
            self._write(f":SOUR:CURR:LEV:IMM {self.current_limit:.6f}")
            self._write(f":SOUR:CURR:VLIM {self.voltage:.4f}")        # 2461 voltage limit
            self._write(f":SENS:VOLT:NPLC {self.nplc:.2f}")
            self._write(':SENS:FUNC "VOLT"')
            self._write(":SENS:VOLT:RANG:AUTO ON")
            self._write(":OUTP:SMOD HIMP")

        # Check nothing went wrong
        if self._check_errors():
            log.warning("Errors after _configure() — check settings")

        log.info("SourceMeter configured: mode=%s  V=%.4f  I=%.4f",
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
            if self.source_mode == "VOLT":
                self._write(f":SOUR:VOLT:LEV:IMM {v:.4f}")
            else:
                self._write(f":SOUR:CURR:VLIM {v:.4f}")
            self._check_errors()

    def set_current_limit(self, a: float):
        self.current_limit = a
        if self._inst:
            if self.source_mode == "VOLT":
                self._write(f":SOUR:VOLT:ILIM {a:.4f}")
            else:
                self._write(f":SOUR:CURR:LEV:IMM {a:.6f}")
            self._check_errors()

    def set_source_mode(self, mode: str):
        self.source_mode = mode.upper()
        if self._inst:
            self._configure()

    # ── Output control ────────────────────────────────────────────────
    def output_on(self):
        if not self._inst:
            raise RuntimeError("SourceMeter not connected")
        self._write(":OUTP ON")
        time.sleep(self.settle_ms / 1000.0)
        self._check_errors()

    def output_off(self):
        if self._inst:
            self._write(":OUTP OFF")

    def measure(self) -> float:
        """
        Returns measured value.
        VOLT source → returns current (A)
        CURR source → returns voltage (V)
        """
        if self.source_mode == "VOLT":
            resp = self._query(":MEAS:CURR?")
        else:
            resp = self._query(":MEAS:VOLT?")

        # 2461 can return comma-separated values — take the first
        val = resp.split(",")[0].strip()
        return float(val)

    def get_output_state(self) -> bool:
        resp = self._query(":OUTP?").strip()
        return resp in ("1", "ON")

    # ── Resource resolver (unchanged) ─────────────────────────────────
    def _resolve_resource(self, resource: str) -> str:
        all_resources = self._rm.list_resources()
        log.debug("All VISA resources found: %s", all_resources)

        if resource in all_resources:
            return resource

        def _normalise(s):
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