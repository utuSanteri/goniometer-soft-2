"""
hardware_mock.py
───────────────────────────────────────────────────────────────────────
Drop-in mock for MotorController, Spectrometer, and SourceMeter.
Produces synthetic but realistic data so every code-path in gui.py and
scan_worker.py can be exercised without any physical hardware.

Swap the import in gui.py:
    from hardware_mock import MotorController, Spectrometer, SourceMeter, OutputVerificationError
"""

import time
import logging
import threading
import numpy as np

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  Shared exception  (mirrors hardware.py)
# ══════════════════════════════════════════════════════════════════════
class SourceMeterError(Exception):
    """Raised when the mock SourceMeter detects an unsafe condition."""


# Alias so gui.py's  `from hardware_mock import … OutputVerificationError`
# also works even though the internal name is SourceMeterError.
OutputVerificationError = SourceMeterError


# ══════════════════════════════════════════════════════════════════════
#  Mock Motor Controller
# ══════════════════════════════════════════════════════════════════════
class MotorController:
    """
    Simulates an Arduino-based two-axis stepper controller.

    Position is tracked internally in steps.  Movement is instantaneous
    (no real delay) so the GUI stays responsive during testing.
    A small configurable latency can be enabled via `move_delay_s`.
    """

    def __init__(self,
                 port: str = "COM_MOCK",
                 baud: int = 115200,
                 timeout: float = 10.0,
                 steps_per_degree: float = 88.89,
                 max_speed: int = 2000,
                 m1_invert: bool = False,
                 m2_invert: bool = False,
                 move_delay_s: float = 0.05):
        self.port              = port
        self.baud              = baud
        self.timeout           = timeout
        self.steps_per_degree  = steps_per_degree
        self.max_speed         = max_speed
        self.m1_invert         = m1_invert
        self.m2_invert         = m2_invert
        self.move_delay_s      = move_delay_s

        self._connected        = False
        self._pos              = [0, 0]   # [motor1_steps, motor2_steps]
        self._speed            = max_speed
        self._lock             = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        time.sleep(0.1)          # mimic the Arduino reset pause
        self._connected = True
        log.info("[MOCK] MotorController connected on %s", self.port)

    def disconnect(self):
        self._connected = False
        log.info("[MOCK] MotorController disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ── Internal helpers ──────────────────────────────────────────────
    def _require_connected(self):
        if not self._connected:
            raise RuntimeError("[MOCK] Motor controller not connected")

    # ── Public API ────────────────────────────────────────────────────
    def move_steps(self, motor: int, steps: int, direction: int):
        """Move motor (1 or 2) by raw steps in direction (0=reverse, 1=forward)."""
        self._require_connected()
        if motor not in (1, 2):
            raise ValueError(f"Invalid motor id: {motor}")

        # Apply inversion flag
        if (motor == 1 and self.m1_invert) or (motor == 2 and self.m2_invert):
            direction = 1 - direction

        signed_steps = steps if direction == 1 else -steps
        with self._lock:
            self._pos[motor - 1] += signed_steps

        time.sleep(self.move_delay_s)
        log.debug("[MOCK] Motor %d moved %+d steps → pos=%d",
                  motor, signed_steps, self._pos[motor - 1])

    def move_degrees(self, motor: int, degrees: float):
        """Move motor by signed degrees (negative = reverse)."""
        self._require_connected()
        steps     = int(round(abs(degrees) * self.steps_per_degree))
        direction = 1 if degrees >= 0 else 0
        self.move_steps(motor, steps, direction)

    def stop(self):
        self._require_connected()
        log.info("[MOCK] Motors stopped")

    def zero(self):
        self._require_connected()
        with self._lock:
            self._pos = [0, 0]
        log.info("[MOCK] Motor positions zeroed")

    def home(self):
        self._require_connected()
        with self._lock:
            self._pos = [0, 0]
        time.sleep(self.move_delay_s * 2)
        log.info("[MOCK] Motors homed to zero")

    def get_position(self) -> tuple:
        """Returns (pos1_steps, pos2_steps)."""
        self._require_connected()
        with self._lock:
            return tuple(self._pos)

    def ping(self) -> bool:
        return self._connected

    def set_speed(self, steps_per_sec: int):
        self._require_connected()
        self._speed = steps_per_sec
        log.info("[MOCK] Motor speed set to %d steps/s", steps_per_sec)


# ══════════════════════════════════════════════════════════════════════
#  Mock Spectrometer
# ══════════════════════════════════════════════════════════════════════
class Spectrometer:
    """
    Simulates an OceanOptics USB2000+ spectrometer.

    Synthetic spectra consist of:
      - A broad background (tungsten-lamp-like blackbody curve)
      - Three Gaussian emission peaks (to give the plot some structure)
      - Gaussian read noise scaled to the integration time

    The spectrum changes slightly with the motor position (angle) so that
    consecutive scan steps produce visibly different plots.
    """

    # Hardware limits for the USB2000+ (milliseconds)
    _MIN_INTTIME_MS = 100.0
    _MAX_INTTIME_MS = 60_000.0

    # Simulated wavelength grid
    _WL_FULL = np.linspace(170.0, 1100.0, 2048)

    def __init__(self,
                 integration_time_ms: float = 100.0,
                 scans_to_average: int = 3,
                 boxcar_width: int = 2,
                 wl_min: float = 200.0,
                 wl_max: float = 1100.0):
        self.integration_time_ms = float(integration_time_ms)
        self.scans_to_average    = max(1, scans_to_average)
        self.boxcar_width        = max(0, boxcar_width)
        self.wl_min              = wl_min
        self.wl_max              = wl_max
        self._connected          = False
        self._dark               = None
        # Vary spectra with "angle" by coupling to motor pos via seed shift
        self._call_counter       = 0

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        time.sleep(0.1)
        self._connected = True
        log.info("[MOCK] Spectrometer connected (USB2000+ simulator)")

    def disconnect(self):
        self._connected = False
        log.info("[MOCK] Spectrometer disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ── Settings ──────────────────────────────────────────────────────
    def set_integration_time(self, ms: float) -> float:
        """
        Clamp to hardware limits and return the value actually set.
        Raises ValueError if the requested value is outside the allowed range,
        matching the behaviour of the real driver.
        """
        if ms < self._MIN_INTTIME_MS:
            # Clamp and raise so the GUI can react
            self.integration_time_ms = self._MIN_INTTIME_MS
            raise ValueError(
                f"Integration time {ms:.2f} ms is below the minimum "
                f"allowed by this device ({self._MIN_INTTIME_MS:.2f} ms).\n"
                f"Value has been clamped to {self._MIN_INTTIME_MS:.2f} ms."
            )
        if ms > self._MAX_INTTIME_MS:
            self.integration_time_ms = self._MAX_INTTIME_MS
            raise ValueError(
                f"Integration time {ms:.2f} ms exceeds the maximum "
                f"allowed by this device ({self._MAX_INTTIME_MS:.2f} ms).\n"
                f"Value has been clamped to {self._MAX_INTTIME_MS:.2f} ms."
            )
        self.integration_time_ms = float(ms)
        log.debug("[MOCK] Integration time set to %.1f ms", ms)
        return self.integration_time_ms

    def set_scans_to_average(self, n: int):
        self.scans_to_average = max(1, int(n))

    def set_boxcar_width(self, w: int):
        self.boxcar_width = max(0, int(w))

    # ── Dark spectrum ─────────────────────────────────────────────────
    def collect_dark(self):
        if not self._connected:
            raise RuntimeError("[MOCK] Spectrometer not connected")
        _, counts = self._acquire_averaged()
        # Dark is just low-level noise — scale down so it doesn't eat real signal
        self._dark = counts * 0.02
        log.info("[MOCK] Dark spectrum collected (%d pixels)", len(self._dark))

    def clear_dark(self):
        self._dark = None
        log.info("[MOCK] Dark spectrum cleared")

    def has_dark(self) -> bool:
        return self._dark is not None

    # ── Internal acquisition ──────────────────────────────────────────
    def _synthetic_spectrum(self, seed_offset: int = 0) -> np.ndarray:
        """
        Generate one frame of synthetic intensity counts.

        Signal scales linearly with integration time (photon accumulation).
        Three Gaussian peaks shift slightly with the seed to simulate
        angular dependence.
        """
        wl   = self._WL_FULL
        rng  = np.random.default_rng(seed=self._call_counter + seed_offset)
        it   = self.integration_time_ms   # longer exposure → more counts

        # ── Background: blackbody-like envelope ───────────────────────
        background = (
            3000 * (it / 100.0)
            * np.exp(-((wl - 900) ** 2) / (2 * 300 ** 2))
        )

        # ── Emission peaks (positions shift subtly with call counter) ─
        peak_shift = (self._call_counter * 0.3) % 20   # ±10 nm drift
        peaks = np.zeros_like(wl)
        for centre, height, width in [
            (450 + peak_shift,  8000 * it / 100.0,  8.0),
            (532,               5000 * it / 100.0, 5.0),
            (780 - peak_shift,  3500 * it / 100.0, 12.0),
        ]:
            peaks += height * np.exp(-((wl - centre) ** 2) / (2 * width ** 2))

        # ── Read noise ────────────────────────────────────────────────
        noise_sigma = max(50.0, 200.0 * (100.0 / it) ** 0.5)
        noise = rng.normal(0, noise_sigma, size=len(wl))

        counts = np.clip(background + peaks + noise, 0, 65535)
        return counts.astype(float)

    def _acquire_averaged(self) -> tuple:
        """Returns (wavelengths, averaged_counts) cropped to [wl_min, wl_max]."""
        frames = [self._synthetic_spectrum(seed_offset=k)
                  for k in range(self.scans_to_average)]
        counts = np.mean(frames, axis=0)

        if self.boxcar_width > 0:
            kernel  = np.ones(2 * self.boxcar_width + 1)
            kernel /= kernel.sum()
            counts  = np.convolve(counts, kernel, mode="same")

        wl   = self._WL_FULL
        mask = (wl >= self.wl_min) & (wl <= self.wl_max)

        self._call_counter += 1
        return wl[mask], counts[mask]

    # ── Public acquisition ────────────────────────────────────────────
    def acquire(self, subtract_dark: bool = True) -> tuple:
        """
        Returns (wavelengths, raw_counts, corrected_counts).
        corrected_counts == raw_counts when no dark is stored or
        subtract_dark=False.
        """
        if not self._connected:
            raise RuntimeError("[MOCK] Spectrometer not connected")

        # Brief pause to simulate integration + readout time
        time.sleep(min(self.integration_time_ms / 1000.0, 0.3))

        wl, raw = self._acquire_averaged()

        if subtract_dark and self._dark is not None:
            n    = len(raw)
            corr = np.clip(raw - self._dark[:n], 0, None)
        else:
            corr = raw.copy()

        return wl, raw, corr


# ══════════════════════════════════════════════════════════════════════
#  Mock Source Meter  (Keithley 2461)
# ══════════════════════════════════════════════════════════════════════
class SourceMeter:
    """
    Simulates a Keithley 2461 source-meter.

    Simulated behaviour
    ───────────────────
    VOLT mode
        measured current  = voltage / simulated_load_ohms  + small noise
        compliance if current >= current_limit × compliance_fraction

    CURR mode
        measured voltage  = current × simulated_load_ohms + small noise
        compliance if voltage >= voltage_limit × compliance_fraction

    You can exercise the verification / error paths by setting the class
    attributes ``fault_mode`` before calling output_on():

        source.fault_mode = "open"        → current too low  (open circuit)
        source.fault_mode = "short"       → compliance hit   (short circuit)
        source.fault_mode = None          → normal operation  (default)
    """

    # Simulated load resistance (Ω)
    _LOAD_OHMS = 50.0

    def __init__(self,
                 resource: str = "MOCK::INSTR",
                 source_mode: str = "VOLT",
                 voltage: float = 5.0,
                 current_limit: float = 0.1,
                 settle_ms: float = 200.0,
                 nplc: float = 1.0,
                 current_threshold: float = 1e-6,
                 voltage_threshold: float = 1e-3,
                 compliance_fraction: float = 0.95,
                 verify_on_output_on: bool = True):
        self.resource             = resource
        self.source_mode          = source_mode.upper()
        self.voltage              = voltage
        self.current_limit        = current_limit
        self.settle_ms            = settle_ms
        self.nplc                 = nplc
        self.current_threshold    = current_threshold
        self.voltage_threshold    = voltage_threshold
        self.compliance_fraction  = compliance_fraction
        self.verify_on_output_on  = verify_on_output_on

        self._connected           = False
        self._output_on           = False
        self._rng                 = np.random.default_rng(seed=42)

        # Set to "open" or "short" to trigger the corresponding error path
        self.fault_mode: str | None = None

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        time.sleep(0.1)
        self._connected = True
        log.info("[MOCK] SourceMeter connected (%s, mode=%s, V=%.3f, I_lim=%.4f)",
                 self.resource, self.source_mode, self.voltage, self.current_limit)

    def disconnect(self):
        if self._output_on:
            self.output_off()
        self._connected = False
        log.info("[MOCK] SourceMeter disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ── Internal helpers ──────────────────────────────────────────────
    def _require_connected(self):
        if not self._connected:
            raise RuntimeError("[MOCK] SourceMeter not connected")

    def _simulated_current(self) -> float:
        """Return a realistic current reading for VOLT source mode."""
        if self.fault_mode == "open":
            # Almost zero — open circuit
            return self._rng.uniform(0, self.current_threshold * 0.1)

        if self.fault_mode == "short":
            # At or above the compliance threshold — short circuit
            return self.current_limit * self.compliance_fraction * 1.05

        # Normal: V/R plus ±0.1 % noise
        base  = self.voltage / self._LOAD_OHMS
        noise = self._rng.normal(0, base * 0.001)
        return abs(base + noise)

    def _simulated_voltage(self) -> float:
        """Return a realistic voltage reading for CURR source mode."""
        if self.fault_mode == "open":
            # Voltage at or above compliance — open circuit for CURR source
            return self.voltage * self.compliance_fraction * 1.05

        if self.fault_mode == "short":
            # Almost zero — short circuit
            return self._rng.uniform(0, self.voltage_threshold * 0.1)

        # Normal: I×R plus ±0.1 % noise
        base  = self.current_limit * self._LOAD_OHMS
        noise = self._rng.normal(0, base * 0.001)
        return abs(base + noise)

    # ── Settings ──────────────────────────────────────────────────────
    def set_voltage(self, v: float):
        self.voltage = v
        log.debug("[MOCK] Voltage set to %.4f V", v)

    def set_current_limit(self, a: float):
        self.current_limit = a
        log.debug("[MOCK] Current limit set to %.6f A", a)

    def set_source_mode(self, mode: str):
        self.source_mode = mode.upper()
        log.info("[MOCK] Source mode set to %s", self.source_mode)

    # ── Output control ────────────────────────────────────────────────
    def output_on(self):
        self._require_connected()
        self._output_on = True
        time.sleep(self.settle_ms / 1000.0)
        log.info("[MOCK] Output ON (settle %.0f ms)", self.settle_ms)
        if self.verify_on_output_on:
            self.verify_operation()

    def output_off(self):
        if self._connected:
            self._output_on = False
            log.info("[MOCK] Output OFF")

    def get_output_state(self) -> bool:
        return self._output_on

    # ── Measurement ───────────────────────────────────────────────────
    def measure(self) -> float:
        """
        Returns simulated measurement:
          - VOLT source → current (A)
          - CURR source → voltage (V)
        """
        self._require_connected()
        if self.source_mode == "VOLT":
            val = self._simulated_current()
        else:
            val = self._simulated_voltage()
        log.debug("[MOCK] Measured %.6g (%s mode)",
                  val, "A" if self.source_mode == "VOLT" else "V")
        return val
    
    def _query(self, cmd: str) -> str:
        """Simulate SCPI query responses for testing."""
        cmd = cmd.strip().upper()
        if "MEAS:VOLT" in cmd:
            v = self._simulated_voltage() if self.source_mode == "CURR" else self.voltage
            i = self._simulated_current() if self.source_mode == "VOLT" else self.current_limit
            return f"{v:.6f},{i:.6f}"
        elif "MEAS:CURR" in cmd:
            i = self._simulated_current()
            v = self.voltage if self.source_mode == "VOLT" else self.current_limit
            return f"{i:.6f},{v:.6f}"
        elif "STAT:QUES" in cmd:
            return "1" if self._is_in_compliance_hw() else "0"
        elif "*IDN?" in cmd:
            return "Keithley Instruments,2461,0,1.0"
        elif "OUTP?" in cmd:
            return "ON" if self._output_on else "OFF"
        elif "SYST:ERR?" in cmd:
            return "+0,"
        else:
            return "OK"


    # ── Verification ──────────────────────────────────────────────────
    def _is_in_compliance_hw(self) -> bool:
        """
        Simulate the hardware compliance bit.
        Trips only when fault_mode forces the measured value over the limit.
        """
        if self.source_mode == "VOLT":
            return (self.fault_mode == "short" and
                    self._simulated_current() >=
                    self.compliance_fraction * self.current_limit)
        else:
            return (self.fault_mode == "open" and
                    self._simulated_voltage() >=
                    self.compliance_fraction * self.voltage)

    def verify_operation(self) -> dict:
        """
        Mirrors the real SourceMeter.verify_operation() exactly.
        Raises SourceMeterError if a fault is detected.
        """
        measured      = self.measure()
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

        soft_limit    = self.compliance_fraction * limit
        signal_ok     = abs(measured) >= threshold
        sw_comp_ok    = abs(measured) < soft_limit
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

        log.info(
            "[MOCK] Verification [%s mode]: measured %s = %.6g %s  "
            "(threshold=%.3g, soft_limit=%.3g, hw_compliance=%s)",
            self.source_mode, quantity, measured, unit,
            threshold, soft_limit, hw_compliance,
        )

        if not signal_ok:
            msg = (
                f"[{self.source_mode} mode] Measured {quantity} "
                f"({measured:.6g} {unit}) is below the minimum expected "
                f"threshold ({threshold:.3g} {unit}).  "
                f"Possible open circuit or disconnected load."
            )
            log.error("[MOCK] %s", msg)
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
            log.error("[MOCK] %s", msg)
            raise SourceMeterError(msg)

        log.info("[MOCK] Verification passed: signal present, no compliance detected.")
        return result
    

class KeysightSourceMeter(SourceMeter):
    """
    Mock for hardware/keysight_sourcemeter.KeysightSourceMeter.

    Constructor signature and public API match the real Keysight driver
    exactly so the mock is a true drop-in replacement.

    Simulation engine (synthetic measurements, fault_mode, compliance
    logic) is inherited unchanged from the mock SourceMeter base class.

    Channel
    -------
    self._ch is carried through all log messages so multi-channel
    scenarios are easy to distinguish in the test output.

    Fault injection
    ---------------
    Inherited from SourceMeter — set ``fault_mode`` before output_on():
        sm.fault_mode = "open"   → signal-too-low path
        sm.fault_mode = "short"  → compliance-trip path
        sm.fault_mode = None     → normal operation  (default)
    """

    def __init__(
        self,
        resource_string: str = "MOCK::GPIB0::1::INSTR",
        channel: int = 1,
        # ── simulation knobs (not present on the real Keysight driver,
        #    but useful for controlling mock behaviour) ────────────────
        source_mode: str = "VOLT",
        voltage: float = 5.0,
        current_limit: float = 0.1,
        settle_ms: float = 200.0,
        nplc: float = 1.0,
        current_threshold: float = 1e-6,
        voltage_threshold: float = 1e-3,
        compliance_fraction: float = 0.95,
        verify_on_output_on: bool = True,
    ) -> None:
        super().__init__(
            resource=resource_string,
            source_mode=source_mode,
            voltage=voltage,
            current_limit=current_limit,
            settle_ms=settle_ms,
            nplc=nplc,
            current_threshold=current_threshold,
            voltage_threshold=voltage_threshold,
            compliance_fraction=compliance_fraction,
            verify_on_output_on=verify_on_output_on,
        )
        # Store Keysight-specific attributes so callers that inspect them
        # (e.g. ConnectTab) get the right values.
        self._resource_string = resource_string
        self._ch = str(channel)

    # ── Connection ────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Simulate opening a VISA session and verifying a B2900-series IDN.
        The fake IDN string contains 'B290' so any real-driver checks that
        look for that substring will pass against this mock too.
        """
        time.sleep(0.1)
        self._connected = True
        _fake_idn = (
            "Keysight Technologies,B2902A,MY00000001,3.0.0-2.0"
        )
        log.info(
            "[MOCK] Keysight SMU connected: %s (channel %s)",
            _fake_idn, self._ch,
        )

    def disconnect(self) -> None:
        if self._output_on:
            self.output_off()
        self._connected = False
        log.info("[MOCK] Keysight SMU disconnected (channel %s)", self._ch)

    # ── Settings ──────────────────────────────────────────────────────

    def set_voltage(self, v: float) -> None:
        """
        Mirrors the real driver: switches to VOLT source mode *and*
        sets the output level in one call.
        """
        self.source_mode = "VOLT"
        self.voltage = v
        log.debug(
            "[MOCK] Keysight ch%s: VOLT source → %.4f V", self._ch, v
        )

    def set_current_limit(self, a: float) -> None:
        """Set the current compliance limit (VOLT source mode)."""
        self.current_limit = a
        log.debug(
            "[MOCK] Keysight ch%s: current compliance → %.6f A", self._ch, a
        )

    def set_source_mode(self, mode: str) -> None:
        self.source_mode = mode.upper()
        log.info(
            "[MOCK] Keysight ch%s: source mode → %s", self._ch, self.source_mode
        )

    # ── Output control ────────────────────────────────────────────────

    def output_on(self) -> None:
        self._require_connected()
        self._output_on = True
        time.sleep(self.settle_ms / 1000.0)
        log.info("[MOCK] Keysight ch%s: output ON", self._ch)
        if self.verify_on_output_on:
            self.verify_operation()

    def output_off(self) -> None:
        if self._connected:
            self._output_on = False
            log.info("[MOCK] Keysight ch%s: output OFF", self._ch)

    def get_output_state(self) -> bool:
        return self._output_on

    # ── Measurement ───────────────────────────────────────────────────

    def measure(self) -> float:
        """
        Complementary quantity to the active source mode:
          VOLT source → returns current (A)
          CURR source → returns voltage (V)
        """
        self._require_connected()
        val = (
            self._simulated_current()
            if self.source_mode == "VOLT"
            else self._simulated_voltage()
        )
        log.debug(
            "[MOCK] Keysight ch%s measured %.6g %s",
            self._ch, val,
            "A" if self.source_mode == "VOLT" else "V",
        )
        return val

    # ── Verification ──────────────────────────────────────────────────

    def verify_operation(self) -> dict:
        """
        Returns the same standardised dict as the mock SourceMeter so
        ScanWorker can use either instrument class interchangeably:

            mode, measured, limit, compliance_hw,
            signal_ok, compliance_ok, ok

        Raises SourceMeterError on open-circuit or compliance conditions,
        matching both the real Keysight driver (post bug-fix) and the
        mock SourceMeter base class.
        """
        measured      = self.measure()
        hw_compliance = self._is_in_compliance_hw()

        if self.source_mode == "VOLT":
            limit, threshold, quantity, unit = (
                self.current_limit, self.current_threshold, "current", "A"
            )
        else:
            limit, threshold, quantity, unit = (
                self.voltage, self.voltage_threshold, "voltage", "V"
            )

        soft_limit    = self.compliance_fraction * limit
        signal_ok     = abs(measured) >= threshold
        sw_comp_ok    = abs(measured) <  soft_limit
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

        log.info(
            "[MOCK] Keysight ch%s [%s mode]: measured %s = %.6g %s  "
            "(threshold=%.3g, soft_limit=%.3g, hw_compliance=%s)",
            self._ch, self.source_mode,
            quantity, measured, unit,
            threshold, soft_limit, hw_compliance,
        )

        if not signal_ok:
            msg = (
                f"[Keysight ch{self._ch} {self.source_mode} mode] "
                f"Measured {quantity} ({measured:.6g} {unit}) is below "
                f"the minimum expected threshold ({threshold:.3g} {unit}). "
                f"Possible open circuit or disconnected load."
            )
            log.error("[MOCK] %s", msg)
            raise SourceMeterError(msg)

        if not compliance_ok:
            reason = (
                "hardware compliance bit is set"
                if hw_compliance
                else (
                    f"measured {quantity} ({measured:.6g} {unit}) "
                    f">= {self.compliance_fraction*100:.0f}% of limit "
                    f"({soft_limit:.6g} {unit})"
                )
            )
            msg = (
                f"[Keysight ch{self._ch} {self.source_mode} mode] "
                f"Source is saturating / in compliance: {reason}. "
                f"Possible short circuit or incorrect limit setting."
            )
            log.error("[MOCK] %s", msg)
            raise SourceMeterError(msg)

        log.info(
            "[MOCK] Keysight ch%s: verification passed — "
            "signal present, no compliance detected.", self._ch
        )
        return result

    # ── Keysight-style SCPI simulation (for unit tests) ───────────────

    def _query(self, cmd: str) -> str:
        """
        Return Keysight-style SCPI responses.

        The channel number is stripped before matching so the same
        logic covers both single- and dual-channel instruments.
        """
        # Normalise: remove channel digit so ":MEAS:CURR? (@1)" →
        # ":MEAS:CURR? (@)"
        cmd_norm = cmd.strip().upper()

        if "MEAS:CURR" in cmd_norm:
            i = self._simulated_current()
            return f"{i:.6E}"

        if "MEAS:VOLT" in cmd_norm:
            v = self._simulated_voltage()
            return f"{v:.6E}"

        if "CURR:PROT:TRIP" in cmd_norm:
            # 1 = compliance tripped, 0 = OK  (Keysight syntax)
            return "1" if self._is_in_compliance_hw() else "0"

        if "*IDN?" in cmd_norm:
            return (
                f"Keysight Technologies,B2902A,"
                f"MY0000000{self._ch},3.0.0-2.0"
            )

        if "OUTP" in cmd_norm and "?" in cmd_norm:
            return "1" if self._output_on else "0"

        if "SYST:ERR" in cmd_norm:
            return '+0,"No error"'

        return "0"