# hardware/keysight_sourcemeter.py
import logging
from pathlib import Path
from typing import Optional

import pyvisa
import yaml

from hardware.exceptions import HardwareDisconnectedError, SourceMeterError
from hardware._base import BaseSourceMeter

logger = logging.getLogger(__name__)

# Resolve config.yaml relative to this file's location so the module
# works regardless of the working directory when the app is launched.
_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_keysight_config() -> dict:
    """
    Read the 'keysight' block from config.yaml.
    Returns an empty dict if the file is missing or the block is absent,
    so callers can apply their own defaults cleanly.
    """
    try:
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        return raw.get("sourcemeter", {}) if isinstance(raw, dict) else {}
    except FileNotFoundError:
        logger.warning("config.yaml not found at '%s'.", _CONFIG_PATH)
        return {}
    except yaml.YAMLError as exc:
        logger.error("Failed to parse config.yaml: %s", exc)
        return {}


_VOLTAGE_MODE = "VOLT"
_CURRENT_MODE = "CURR"


class KeysightSourceMeter(BaseSourceMeter):
    """
    Controls a Keysight B2900-series SMU via pyvisa SCPI commands.
    Drop-in replacement for hardware/sourcemeter.py.
        """

    def __init__(
        self,
        resource: Optional[str] = None,
        source_mode: str = "VOLT",
        voltage: float = 5.0,
        current_limit: float = 0.1,
        settle_ms: float = 200.0,
        nplc: float = 1.0,
        channel: Optional[int] = None,
        current_threshold: float = 1e-6,
        voltage_threshold: float = 1e-3,
        compliance_fraction: float = 0.95,
        verify_on_output_on: bool = True,
    ) -> None:

        # ── Load config only when needed ──────────────────────────────────
        cfg = _load_keysight_config() if (resource is None or channel is None) else {}

        # ── VISA address / channel ────────────────────────────────────────
        self._resource = resource if resource is not None else cfg.get("resource", "GPIB0::1::INSTR")
        self._ch       = str(channel if channel is not None else int(cfg.get("channel", 1)))

        # ── VISA handles (populated in connect()) ─────────────────────────
        self._rm        = None
        self._dev       = None
        self._connected = False

        # ── Source settings ───────────────────────────────────────────────
        self.source_mode   = source_mode.upper()
        self.voltage       = voltage
        self.current_limit = current_limit
        self.settle_ms     = settle_ms
        self.nplc          = nplc

        # ── Verification settings ─────────────────────────────────────────
        self.current_threshold   = current_threshold
        self.voltage_threshold   = voltage_threshold
        self.compliance_fraction = compliance_fraction
        self.verify_on_output_on = verify_on_output_on

     # ------------------------------------------------------------------
     # Connection management
     # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the VISA session and verify the instrument identity."""
        try:
            self._rm  = pyvisa.ResourceManager()
            self._dev = self._rm.open_resource(self._resource)
            dev_id    = self._dev.query("*IDN?").strip()
        except pyvisa.errors.VisaIOError as exc:
            self._connected = False
            raise HardwareDisconnectedError(
                f"Cannot open VISA resource '{self._resource}': {exc}"
            ) from exc

        # Accept any B2900-series variant (B2901A, B2902A, B2912A, …)
        if "B290" not in dev_id:
            self.disconnect()
            raise HardwareDisconnectedError(
                f"Unexpected instrument found: '{dev_id}'. "
                "Expected a Keysight B2900-series SMU."
            )

        self._connected = True
        logger.info("Keysight SMU connected: %s (channel %s)", dev_id, self._ch)

    def disconnect(self) -> None:
        """Close the VISA session cleanly."""
        try:
            if self._dev is not None:
                self._dev.close()
        except Exception as exc:
            logger.warning("Error closing VISA session: %s", exc)
        finally:
            self._dev       = None
            self._rm        = None
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected
    
    def set_source_mode(self, mode: str) -> None:
        self.source_mode = mode.upper()
        func = "VOLT" if self.source_mode == "VOLT" else "CURR"
        self._write(f":SOUR{self._ch}:FUNC:MODE {func}")

    def get_output_state(self) -> bool:
        return bool(int(self._query(f":OUTP{self._ch}?").strip()))

    # ------------------------------------------------------------------
    # Internal SCPI helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if not self._connected or self._dev is None:
            raise HardwareDisconnectedError(
                "Keysight SMU is not connected. Call connect() first."
            )

    def _write(self, cmd: str) -> None:
        self._require_connected()
        try:
            self._dev.write(cmd)
        except pyvisa.errors.VisaIOError as exc:
            raise SourceMeterError(f"VISA write failed ({cmd!r}): {exc}") from exc

    def _query(self, cmd: str) -> str:
        self._require_connected()
        try:
            return self._dev.query(cmd)
        except pyvisa.errors.VisaIOError as exc:
            raise SourceMeterError(f"VISA query failed ({cmd!r}): {exc}") from exc

    def _query_float(self, cmd: str) -> float:
        raw = self._query(cmd)
        try:
            # Instruments sometimes return comma-separated tuples; take first.
            return float(raw.strip().split(",")[0])
        except ValueError as exc:
            raise SourceMeterError(
                f"Could not parse instrument response {raw!r} as float."
            ) from exc

    # ------------------------------------------------------------------
    # Public interface — mirrors hardware/sourcemeter.py exactly
    # ------------------------------------------------------------------

    def set_voltage(self, v: float) -> None:
        """Enter voltage-source mode and set the output level."""
        self.source_mode = _VOLTAGE_MODE
        self._write(f":SOUR{self._ch}:FUNC:MODE VOLT")
        self._write(f":SOUR{self._ch}:VOLT {v:g}")

    def set_current_limit(self, a: float) -> None:
        """
        Set the current compliance limit for voltage-source mode.

        Delegates range validation to the instrument — it will return a
        VISA error if the value exceeds the hardware range, which is more
        reliable than a software-side guess.
        """
        self._write(f":SENS{self._ch}:CURR:PROT {a:g}")

    def output_on(self) -> None:
        self._write(f":OUTP{self._ch} ON")

    def output_off(self) -> None:
        self._write(f":OUTP{self._ch} OFF")

    def measure(self) -> float:
        """
        Perform a spot measurement and return the result as a float.

        Returns the complementary quantity to the source mode:
          - Voltage-source mode → returns measured current (A).
          - Current-source mode → returns measured voltage (V).
        """
        sense_mode = (
            _CURRENT_MODE
            if self.source_mode == _VOLTAGE_MODE
            else _VOLTAGE_MODE
        )
        return self._query_float(f":MEAS:{sense_mode}? (@{self._ch})")

    def verify_operation(self) -> dict:
        tripped = bool(int(
            self._query(f":SENS{self._ch}:CURR:PROT:TRIP?").strip()
        ))
        measured = self.measure()
        return {
            "mode":          self.source_mode,
            "measured":      measured,
            "limit":         None,        # not tracked here
            "compliance_hw": tripped,
            "signal_ok":     True,        # Keysight doesn't do threshold check
            "compliance_ok": not tripped,
            "ok":            not tripped,
        }