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

            # Storage
            all_wavelengths = None
            data_rows = []   # each row: [angle, raw..., corr...]

            # ── Move to start angle ───────────────────────────────────
            self._status(f"Moving to start angle {ang_start}°...")
            self.motor.move_degrees(motor_id, ang_start)
            self._check_stop()

            prev_angle = ang_start

            for i, angle in enumerate(angles):
                self._check_stop()

                # Move delta from previous position
                if i > 0:
                    delta = angle - prev_angle
                    self._status(f"Moving {delta:+.3f}° → {angle:.3f}°")
                    self.motor.move_degrees(motor_id, delta)
                    self._check_stop()
                prev_angle = angle

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
                if all_wavelengths is None:        #remove if affects real scan, here for the mock
                    all_wavelengths = wl         #remove if affects real scan, here for the mock
                self._status(f"  Measured: V={meas_v:.4f}, I={meas_i:.6f}  (peak corr: {corr.max():.1f} cts)")

                # 4. Power OFF
                self.sourcemeter.output_off()
                self._status(f"  Output OFF")

                # 5. Build row matching _save()'s expected format:
                # [angle, V, I, comp, raw..., corr...]
                row = [angle, meas_v, meas_i, comp_flag] + raw.tolist() + corr.tolist()
                data_rows.append(row)


                # Notify GUI
                if "on_spectrum" in self.cb:
                    self.cb["on_spectrum"](angle, wl, corr)
                if "on_progress" in self.cb:
                    self.cb["on_progress"](i + 1, total, angle)

            # ── Save data ─────────────────────────────────────────────
            path_spec, path_src = self._save(all_wavelengths, data_rows, p)
            self._status(
                f"Scan complete.\n"
                f"  Spectra    : {path_spec}\n"
                f"  Sourcemeter: {path_src}"
            )
            if "on_finished" in self.cb:
                self.cb["on_finished"]((path_spec, path_src))

        except InterruptedError as e:
            self._status(f"Scan interrupted: {e}")
            self.sourcemeter.output_off()
            if "on_finished" in self.cb:
                self.cb["on_finished"](None)

        except Exception as e:
            log.exception("Scan error")
            self.sourcemeter.output_off()
            if "on_error" in self.cb:
                self.cb["on_error"](e)

# ── Data saving ───────────────────────────────────────────────────
    def _save(self, wavelengths, rows, p) -> str:
        save_dir             = p.get("save_dir", "./data")
        filename_spectrum    = p.get("filename", "scan_data")
        filename_sourcemeter = filename_spectrum + "_sourcemeter"
        delimiter            = p.get("delimiter", ";")
        timestamp            = p.get("timestamp_in_filename", True)

        os.makedirs(save_dir, exist_ok=True)

        if timestamp:
            ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname_spec = f"{filename_spectrum}_{ts}.txt"
            fname_src  = f"{filename_sourcemeter}_{ts}.txt"
        else:
            fname_spec = f"{filename_spectrum}.txt"
            fname_src  = f"{filename_sourcemeter}.txt"

        full_path_spectrum    = os.path.join(save_dir, fname_spec)
        full_path_sourcemeter = os.path.join(save_dir, fname_src)

        # ── Sanity check pixel count against actual data ──────────────────
        wl = wavelengths
        n  = len(wl)

        for i, row in enumerate(rows):
            expected = 4 + 2 * n          # angle, V, I, comp, raw×n, corr×n
            if len(row) != expected:
                n_actual = (len(row) - 4) // 2
                log.warning("Row %d has %d cols, expected %d — "
                            "trimming wavelengths %d → %d",
                            i, len(row), expected, n, n_actual)
                n  = n_actual
                wl = wavelengths[:n]
                break

        now = datetime.now().isoformat()

        # ── Spectrometer file ─────────────────────────────────────────────
        header_spectrum = [
            f"# Spectroscopy Scan Data — Spectrometer",
            f"# Date             : {now}",
            f"# Angles           : {p['angle_start']} to {p['angle_end']} "
            f"step {p['angle_step']} deg",
            f"# Int. time        : {self.spectrometer.integration_time_ms} ms",
            f"# Averages         : {self.spectrometer.scans_to_average}",
            f"# Boxcar           : {self.spectrometer.boxcar_width}",
            f"# Dark subtraction : {p.get('subtract_dark', True)}",
            f"# Wavelength range : {wl[0]:.2f} - {wl[-1]:.2f} nm",
            f"# Pixels           : {n}",
            f"#",
            f"# Row layout:",
            f"#  Row 1              : Wavelengths (nm) with 'angle_deg' in col 0",
            f"#  Rows 2 to {len(rows)+1}       : Raw counts per angle",
            f"#  Rows {len(rows)+2} to {2*len(rows)+1} : Corrected counts per angle",
            f"#"
        ]

        with open(full_path_spectrum, "w") as f:
            f.write("\n".join(header_spectrum) + "\n")
            
            # Row 1: Wavelengths
            wavelength_row = ["angle_deg"] + [f"{w:.4f}" for w in wl]
            f.write(delimiter.join(wavelength_row) + "\n")

            # Rows 2 to N: Raw counts
            for row in rows:
                angle = row[0]
                raw   = row[4 : 4 + n]
                out   = [angle] + raw
                f.write(delimiter.join(f"{v:.6g}" for v in out) + "\n")

            # Rows N+1 to M: Corrected counts
            for row in rows:
                angle = row[0]
                corr  = row[4 + n : 4 + 2 * n]
                out   = [angle] + corr
                f.write(delimiter.join(f"{v:.6g}" for v in out) + "\n")

        log.info("Spectrum data saved to %s", full_path_spectrum)

        # ── Sourcemeter file ──────────────────────────────────────────────
        header_sourcemeter = [
            f"# Spectroscopy Scan Data — Source Meter",
            f"# Date             : {now}",
            f"# Angles           : {p['angle_start']} to {p['angle_end']} "
            f"step {p['angle_step']} deg",
            f"# Source mode      : {self.sourcemeter.source_mode}",
            f"# Voltage setpoint : {self.sourcemeter.voltage} V",
            f"# Current limit    : {self.sourcemeter.current_limit} A",
            f"#",
            f"# Column layout:",
            f"#  Col 0 : Angle (deg)",
            f"#  Col 1 : Measured voltage (V)",
            f"#  Col 2 : Measured current (A)",
            f"#  Col 3 : In compliance (0=no 1=yes)",
        ]

        col_names_sourcemeter = [
            "angle_deg", "voltage_V", "current_A", "in_compliance"
        ]

        with open(full_path_sourcemeter, "w") as f:
            f.write("\n".join(header_sourcemeter) + "\n")
            f.write(delimiter.join(col_names_sourcemeter) + "\n")
            for row in rows:
                angle  = row[0]
                volt   = row[1]
                curr   = row[2]
                comp   = row[3]
                f.write(delimiter.join(
                    f"{v:.6g}" for v in [angle, volt, curr, comp]) + "\n")

        log.info("Sourcemeter data saved to %s", full_path_sourcemeter)

        # Return both paths as a tuple
        return full_path_spectrum, full_path_sourcemeter