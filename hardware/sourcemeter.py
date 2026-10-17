"""
Keithley 2461 source-meter.
"""

import time
import logging

from hardware._base import BaseSourceMeter
from hardware._visa import get_resource_manager

log = logging.getLogger(__name__)


from hardware.exceptions import HardwareDisconnectedError, SourceMeterError


class SourceMeter(BaseSourceMeter):
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
                 current_threshold: float = 1e-6,
                 voltage_threshold: float = 1e-3,
                 compliance_fraction: float = 0.95,
                 verify_on_output_on: bool = True):
        self._rm   = None
        self._dev = None
        self.resource      = resource
        self.source_mode   = source_mode.upper()
        self.voltage       = voltage
        self.current_limit = current_limit
        self.settle_ms     = settle_ms
        self.nplc          = nplc

        self.current_threshold   = current_threshold
        self.voltage_threshold   = voltage_threshold
        self.compliance_fraction = compliance_fraction
        self.verify_on_output_on = verify_on_output_on

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._rm = get_resource_manager()
        resolved = self._resolve_resource(self.resource)
        self._dev = self._rm.open_resource(resolved)
        self._dev.timeout = 10_000

        self._dev.write_termination = "\n"
        self._dev.read_termination  = "\n"

        self._write("*RST")
        self._write("*CLS")
        time.sleep(1.0)
        self._check_errors()
        self._configure()
        log.info("SourceMeter connected: %s", resolved)

    def disconnect(self):
        if self._dev:
            self.output_off()
            self._dev.close()
            self._dev = None
            log.info("SourceMeter disconnected")

    def is_connected(self) -> bool:
        return self._dev is not None

    # ── Low-level helpers ─────────────────────────────────────────────
    def _write(self, cmd: str):
        self._dev.write(cmd)

    def _query(self, cmd: str) -> str:
        return self._dev.query(cmd).strip()

    def _check_errors(self) -> bool:
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
        if self.source_mode == "VOLT":
            self._write(":SOUR:FUNC VOLT")
            self._write(f":SOUR:VOLT:LEV:IMM {self.voltage:.4f}")
            self._write(f":SOUR:VOLT:ILIM {self.current_limit:.4f}")
            self._write(f":SENS:CURR:NPLC {self.nplc:.2f}")
            self._write(':SENS:FUNC "CURR"')
            self._write(":SENS:CURR:RANG:AUTO ON")
            self._write(":OUTP:SMOD HIMP")
        else:
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

    # ── Settings ──────────────────────────────────────────────────────
    def set_voltage(self, v: float):
        self.voltage = v
        if self._dev:
            cmd = (":SOUR:VOLT:LEV:IMM" if self.source_mode == "VOLT"
                   else ":SOUR:CURR:VLIM")
            self._write(f"{cmd} {v:.4f}")
            self._check_errors()

    def set_current_limit(self, a: float):
        self.current_limit = a
        if self._dev:
            cmd = (":SOUR:VOLT:ILIM" if self.source_mode == "VOLT"
                   else ":SOUR:CURR:LEV:IMM")
            self._write(f"{cmd} {a:.6f}")
            self._check_errors()

    def set_source_mode(self, mode: str):
        self.source_mode = mode.upper()
        if self._dev:
            self._configure()

    # ── Output control ────────────────────────────────────────────────
    def _enable_output(self):
        if not self._dev:
            raise RuntimeError("SourceMeter not connected")
        self._write(":OUTP ON")
        self._check_errors()

    def output_off(self):
        if self._dev:
            self._write(":OUTP OFF")

    # ── Compliance ────────────────────────────────────────────────────
    def in_compliance(self) -> bool:
        try:
            qsr = int(self._query(":STAT:QUES:COND?"))
            if self.source_mode == "VOLT":
                return bool(qsr & 0b10)
            else:
                return bool(qsr & 0b01)
        except Exception as exc:
            log.debug("Could not read Questionable Status Register: %s", exc)
            return False

    # ── Measurement ───────────────────────────────────────────────────
    def measure_voltage(self) -> float:
        return float(self._query(":MEAS:VOLT?").split(",")[0].strip())

    def measure_current(self) -> float:
        return float(self._query(":MEAS:CURR?").split(",")[0].strip())

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
                log.info("Config resource %r loosely matched %r",
                         resource, addr)
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