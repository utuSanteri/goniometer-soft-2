"""
data_worker.py
───────────────────────────────────────────────────────────────────────
Handles data saving for spectroscopy scans.
"""

import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

class DataWorker:
    """
    Encapsulates the logic for saving spectroscopy and sourcemeter data.
    """

    def __init__(self,
                 params: dict,
                 spectrometer,
                 sourcemeter):
        self.params = params
        self.spectrometer = spectrometer
        self.sourcemeter = sourcemeter

    def save(self, wavelengths, rows) -> tuple[str, str]:
        """
        Saves spectroscopy and sourcemeter data to files.
        Returns (path_to_spectrometer_file, path_to_sourcemeter_file).
        """
        save_dir             = self.params.get("save_dir", "./data")
        filename_spectrum    = self.params.get("filename", "scan_data")
        filename_sourcemeter = filename_spectrum + "_sourcemeter"
        delimiter            = self.params.get("delimiter", ";")
        timestamp            = self.params.get("timestamp_in_filename", True)

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
            f"# Angles           : {self.params['angle_start']} to {self.params['angle_end']} "
            f"step {self.params['angle_step']} deg",
            f"# Int. time        : {self.spectrometer.integration_time_ms} ms",
            f"# Averages         : {self.spectrometer.scans_to_average}",
            f"# Boxcar           : {self.spectrometer.boxcar_width}",
            f"# Dark subtraction : {self.params.get('subtract_dark', True)}",
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
            f"# Angles           : {self.params['angle_start']} to {self.params['angle_end']} "
            f"step {self.params['angle_step']} deg",
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
                f.write(delimiter.join(f"{v:.6g}" for v in [row[0], row[1], row[2], row[3]]) + "\n")

        log.info("Sourcemeter data saved to %s", full_path_sourcemeter)

        # Return both paths as a tuple
        return full_path_spectrum, full_path_sourcemeter