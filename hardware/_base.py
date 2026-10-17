"""
Abstract base classes for every instrument category.

Mock implementations and alternative hardware drivers should subclass
these so that type-checking and interface compliance are enforced.
"""

import time
import logging
from abc import ABC, abstractmethod

from hardware.exceptions import SourceMeterError

log = logging.getLogger(__name__)


class BaseMotorController(ABC):
    """Interface that every motor controller must implement."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def move_steps(self, motor: int, steps: int, direction: int): ...

    @abstractmethod
    def move_degrees(self, motor: int, degrees: float): ...

    @abstractmethod
    def move_to_degrees(self, motor: int, degrees: float): ...

    @abstractmethod
    def stop(self): ...

    @abstractmethod
    def zero(self): ...

    @abstractmethod
    def home(self): ...

    @abstractmethod
    def get_position(self) -> tuple: ...

    @abstractmethod
    def get_angle(self, motor: int) -> float: ...

    @abstractmethod
    def ping(self) -> bool: ...

    @abstractmethod
    def set_speed(self, steps_per_sec: int): ...


class BaseSpectrometer(ABC):
    """Interface that every spectrometer must implement."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_integration_time(self, ms: float): ...

    @abstractmethod
    def set_scans_to_average(self, n: int): ...

    @abstractmethod
    def set_boxcar_width(self, w: int): ...

    @abstractmethod
    def collect_dark(self): ...

    @abstractmethod
    def clear_dark(self): ...

    @abstractmethod
    def acquire(self, subtract_dark: bool = True) -> tuple: ...

    @abstractmethod
    def has_dark(self) -> bool: ...


class BaseSourceMeter(ABC):
    """
    Interface that every source-meter must implement.

    Drivers implement the instrument-specific primitives (the abstract
    methods). Settling, picking the measured quantity and the
    open/short/compliance check after Output ON are shared here, so
    every instrument behaves the same.

    Drivers must set: source_mode ("VOLT" or "CURR"), voltage,
    current_limit, settle_ms, current_threshold, voltage_threshold,
    compliance_fraction, verify_on_output_on.
    """

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_voltage(self, v: float): ...

    @abstractmethod
    def set_current_limit(self, a: float): ...

    @abstractmethod
    def set_source_mode(self, mode: str): ...

    @abstractmethod
    def _enable_output(self):
        """Switch the output on. No settling or checks."""

    @abstractmethod
    def output_off(self): ...

    @abstractmethod
    def get_output_state(self) -> bool: ...

    @abstractmethod
    def measure_voltage(self) -> float: ...

    @abstractmethod
    def measure_current(self) -> float: ...

    @abstractmethod
    def in_compliance(self) -> bool:
        """The instrument's own compliance flag for the active mode."""

    # ── Shared behaviour ──────────────────────────────────────────────
    def output_on(self):
        """Output on, wait settle_ms, then verify (if enabled)."""
        self._enable_output()
        time.sleep(self.settle_ms / 1000.0)
        if self.verify_on_output_on:
            self.verify_operation()

    def measure(self) -> float:
        """The complementary quantity: current in VOLT mode, voltage in
        CURR mode."""
        if self.source_mode == "VOLT":
            return self.measure_current()
        return self.measure_voltage()

    def verify_operation(self) -> dict:
        """
        Measure the output and verify two conditions:

        1. **Signal present** – the measured quantity is above a minimum
           threshold, confirming the circuit is complete.
        2. **No compliance / saturation** – the measured quantity is below
           ``compliance_fraction`` × the configured limit *and* the
           instrument's own compliance bit is not set.

        Returns a result dict with keys: mode, measured, limit,
        compliance_hw, signal_ok, compliance_ok, ok.

        Raises SourceMeterError if either check fails.
        """
        measured = self.measure()
        hw_compliance = self.in_compliance()

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
            "Verification [%s mode]: measured %s = %.6g %s  "
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
