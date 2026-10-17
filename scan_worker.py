"""
scan_worker.py
───────────────────────────────────────────────────────────────────────
Runs the automated angle scan in a background thread.
Communicates with the GUI via callbacks / Qt signals.
"""

import os
import time
import logging
import threading
import numpy as np
from datetime import datetime
from data_worker import DataWorker

log = logging.getLogger(__name__)


class ScanWorker:
    """
    Executes the full scan sequence in a daemon thread.

    Callbacks (all called from the worker thread - GUI must be thread-safe):
        on_progress(current_step, total_steps, angle_deg)
        on_spectrum(angle_deg, wavelengths, corrected_counts)
        on_status(message: str)
        on_finished(saved_path: str | None)
        on_error(exception: Exception)
    """

    def __init__(self,
                 motor,          # MotorController
                 spectrometer,   # Spectrometer
                 sourcemeter,    # SourceMeter
                 params: dict,   # scan parameters from GUI
                 callbacks: dict):
        self.motor = motor
        self.spectrometer = spectrometer
        self.sourcemeter = sourcemeter
        self.params = params
        self.cb = callbacks
        self.data_worker = DataWorker(params, spectrometer, sourcemeter)
        self._stop_event = threading.Event()
        self._thread = None

    # ── Control ───────────────────────────────────────────────────────
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.sourcemeter.output_off()   # safety: turn off immediately

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Helpers ───────────────────────────────────────────────────────
    def _status(self, msg):
        log.info(msg)
        if "on_status" in self.cb:
            self.cb["on_status"](msg)

    def _keep_partial(self, reason: str):
        """Marks the files as incomplete and tells the user where they are."""
        try:
            self.data_worker.finish(reason)
        except Exception:
            log.exception("Could not write end note to data files")
        if self.data_worker.is_open():
            self._status(
                f"Partial data kept ({reason}).\n"
                f"  Spectra    : {self.data_worker.path_spectrum}\n"
                f"  Sourcemeter: {self.data_worker.path_sourcemeter}")
        else:
            self._status("No angles were completed, nothing saved.")

    def _check_stop(self):
        if self._stop_event.is_set():
            raise InterruptedError("Scan stopped by user")

    # ── Main sequence ─────────────────────────────────────────────────
    def _run(self):
        try:
            p = self.params
            ang_start  = float(p["angle_start"])
            ang_end    = float(p["angle_end"])
            ang_step   = float(p["angle_step"])
            motor_id   = int(p.get("motor_id", 1))
            subtract_dark = bool(p.get("subtract_dark", True))

            # Build angle list
            angles = []
            a = ang_start
            if ang_step == 0:
                raise ValueError("Angle step cannot be zero")
            while (ang_step > 0 and a <= ang_end + 1e-9) or \
                  (ang_step < 0 and a >= ang_end - 1e-9):
                angles.append(round(a, 6))
                a += ang_step

            total = len(angles)
            if total == 0:
                raise ValueError("No angles to scan. Check start/end/step.")

            self._status(f"Scan starting: {total} angles "
                         f"[{ang_start}° → {ang_end}° step {ang_step}°]")

            for i, angle in enumerate(angles):
                self._check_stop()

                # Absolute move: angles are measured from the user-set zero
                self._status(f"Moving to {angle:.3f}°")
                self.motor.move_to_degrees(motor_id, angle)
                actual = self.motor.get_angle(motor_id)
                self._check_stop()

                # ── Power ON ──────────────────────────────────────────
                self._status(f"[{i+1}/{total}] Angle {angle:.3f}° — output ON")
                self.sourcemeter.output_on()
                self._check_stop()

                # 1. Capture both measured Voltage and Current
                # (measure() only returns one quantity, so we query both explicitly)
                meas_v = float(self.sourcemeter._query(":MEAS:VOLT?").split(",")[0].strip())
                meas_i = float(self.sourcemeter._query(":MEAS:CURR?").split(",")[0].strip())

                # 2. Capture compliance status explicitly as 0 or 1
                try:
                    qsr = int(self.sourcemeter._query(":STAT:QUES:COND?"))
                    bit_mask = 0b10 if self.sourcemeter.source_mode == "VOLT" else 0b01
                    comp_flag = int(bool(qsr & bit_mask))
                except Exception:
                    comp_flag = 0

                # 3. Collect spectrum
                wl, raw, corr = self.spectrometer.acquire(subtract_dark=subtract_dark)
                self._status(f"  Measured: V={meas_v:.4f}, I={meas_i:.6f}  (peak corr: {corr.max():.1f} cts)")

                # 4. Power OFF
                self.sourcemeter.output_off()
                self._status(f"  Output OFF")

                # 5. Write this angle to disk now, so a stop/error keeps it
                if not self.data_worker.is_open():
                    self.data_worker.open(wl)
                self.data_worker.append(actual, angle, meas_v, meas_i,
                                        comp_flag, raw, corr)

                # Notify GUI
                if "on_spectrum" in self.cb:
                    self.cb["on_spectrum"](actual, wl, corr)
                if "on_progress" in self.cb:
                    self.cb["on_progress"](i + 1, total, actual)

            path_spec = self.data_worker.path_spectrum
            path_src  = self.data_worker.path_sourcemeter
            self._status(
                f"Scan complete.\n"
                f"  Spectra    : {path_spec}\n"
                f"  Sourcemeter: {path_src}"
            )
            if "on_finished" in self.cb:
                self.cb["on_finished"]((path_spec, path_src))

        except InterruptedError as e:
            self.sourcemeter.output_off()
            self._status(f"Scan interrupted: {e}")
            self._keep_partial("stopped by user")
            if "on_finished" in self.cb:
                self.cb["on_finished"](None)

        except Exception as e:
            log.exception("Scan error")
            self.sourcemeter.output_off()
            self._keep_partial(f"error: {e}")
            if "on_error" in self.cb:
                self.cb["on_error"](e)

