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

                # ── Collect spectrum ──────────────────────────────────
                wl, raw, corr = self.spectrometer.acquire(
                    subtract_dark=subtract_dark)
                measured = self.sourcemeter.measure()
                self._status(f"  Measured: {measured:.4f}  "
                             f"(peak corr: {corr.max():.1f} cts)")

                # ── Power OFF ─────────────────────────────────────────
                self.sourcemeter.output_off()
                self._status(f"  Output OFF")

                # Store
                if all_wavelengths is None:
                    all_wavelengths = wl
                row = [angle, measured] + raw.tolist() + corr.tolist()
                data_rows.append(row)

                # Notify GUI
                if "on_spectrum" in self.cb:
                    self.cb["on_spectrum"](angle, wl, corr)
                if "on_progress" in self.cb:
                    self.cb["on_progress"](i + 1, total, angle)

            # ── Save data ─────────────────────────────────────────────
            path = self._save(all_wavelengths, data_rows, p)
            self._status(f"Scan complete. Data saved to:\n  {path}")
            if "on_finished" in self.cb:
                self.cb["on_finished"](path)

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
        save_dir  = p.get("save_dir", "./data")
        filename  = p.get("filename", "scan_data")
        delimiter = p.get("delimiter", ";")
        timestamp = p.get("timestamp_in_filename", True)
    
        os.makedirs(save_dir, exist_ok=True)
    
        if timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{filename}_{ts}.txt"
        else:
            fname = f"{filename}.txt"
    
        full_path = os.path.join(save_dir, fname)
    
        wl = wavelengths
        n  = len(wl)
    
        # ── Sanity check: all rows must match the wavelength length ───────
        for i, row in enumerate(rows):
            # row = [angle, voltage, current, compliance, raw×n, corr×n]
            expected = 4 + 2 * n
            if len(row) != expected:
                actual_n = (len(row) - 4) // 2
                # Trim the wavelength array to match the data
                print(f"Warning: row {i} has {len(row)} cols, "
                      f"expected {expected}. "
                      f"Trimming wavelengths {n} → {actual_n}")
                n  = actual_n
                wl = wavelengths[:n]
                break
            
        header_lines = [
            f"# Spectroscopy Scan Data",
            f"# Date       : {datetime.now().isoformat()}",
            f"# Angles     : {p['angle_start']} to {p['angle_end']} "
            f"step {p['angle_step']} deg",
            f"# Source mode: {self.sourcemeter.source_mode}",
            f"# Voltage    : {self.sourcemeter.voltage} V",
            f"# Curr limit : {self.sourcemeter.current_limit} A",
            f"# Int. time  : {self.spectrometer.integration_time_ms} ms",
            f"# Averages   : {self.spectrometer.scans_to_average}",
            f"# Boxcar     : {self.spectrometer.boxcar_width}",
            f"# Dark sub.  : {p.get('subtract_dark', True)}",
            f"# Wavelength range: {wl[0]:.2f} - {wl[-1]:.2f} nm",
            f"# Pixels     : {n}",
            f"#",
            f"# Column layout:",
            f"#  Col 0      : Angle (deg)",
            f"#  Col 1      : Voltage (V)",
            f"#  Col 2      : Current (A)",
            f"#  Col 3      : In compliance (0/1)",
            f"#  Col 4..{n+3}  : Raw counts per wavelength pixel",
            f"#  Col {n+4}..{2*n+3}: Dark-corrected counts per wavelength pixel",
            f"#",
            "# wavelength_nm: " + delimiter.join(f"{w:.4f}" for w in wl),
        ]
    
        col_names = (
            ["angle_deg", "voltage_V", "current_A", "in_compliance"] +
            [f"raw_{i}"  for i in range(n)] +
            [f"corr_{i}" for i in range(n)]
        )
    
        with open(full_path, "w") as f:
            f.write("\n".join(header_lines) + "\n")
            f.write(delimiter.join(col_names) + "\n")
            for row in rows:
                # trim row to expected length in case of any mismatch
                f.write(delimiter.join(f"{v:.6g}" for v in row[:4 + 2 * n]) + "\n")
    
        log.info("Data saved to %s", full_path)
        return full_path