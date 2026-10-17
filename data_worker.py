"""
data_worker.py
───────────────────────────────────────────────────────────────────────
Handles data saving for spectroscopy scans.

Data is appended to disk one angle at a time, so a scan that is stopped
or fails keeps everything measured up to that point.
"""

import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# Written into the spectrum file header so loaders can tell this
# per-angle layout from the older stacked (all raw, then all corrected)
# layout.
FORMAT_TAG = "per-angle v2"


class DataWorker:
    """
    Writes spectroscopy and sourcemeter data for one scan.

    Usage:
        dw.open(wavelengths)     # creates both files, writes headers
        dw.append(...)           # once per angle, flushed to disk
        dw.finish(note)          # optional trailing note (e.g. aborted)
    """

    def __init__(self,
                 params: dict,
                 spectrometer,
                 sourcemeter):
        self.params = params
        self.spectrometer = spectrometer
        self.sourcemeter = sourcemeter
        self.delimiter = params.get("delimiter", ";")
        self.n_pixels = None
        self.path_spectrum = None
        self.path_sourcemeter = None

    def is_open(self) -> bool:
        return self.path_spectrum is not None

    def open(self, wavelengths) -> tuple[str, str]:
        """
        Creates both files and writes their headers.
        Returns (path_to_spectrometer_file, path_to_sourcemeter_file).
        """
        save_dir             = self.params.get("save_dir", "./data")
        filename_spectrum    = self.params.get("filename", "scan_data")
        filename_sourcemeter = filename_spectrum + "_sourcemeter"
        timestamp            = self.params.get("timestamp_in_filename", True)
        d                    = self.delimiter

        os.makedirs(save_dir, exist_ok=True)

        if timestamp:
            ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname_spec = f"{filename_spectrum}_{ts}.txt"
            fname_src  = f"{filename_sourcemeter}_{ts}.txt"
        else:
            fname_spec = f"{filename_spectrum}.txt"
            fname_src  = f"{filename_sourcemeter}.txt"

        self.path_spectrum    = os.path.join(save_dir, fname_spec)
        self.path_sourcemeter = os.path.join(save_dir, fname_src)

        wl = wavelengths
        self.n_pixels = len(wl)
        now = datetime.now().isoformat()
        p = self.params

        # ── Spectrometer file ─────────────────────────────────────────────
        header_spectrum = [
            f"# Spectroscopy Scan Data — Spectrometer",
            f"# Format           : {FORMAT_TAG}",
            f"# Date             : {now}",
            f"# Angles           : {p['angle_start']} to {p['angle_end']} "
            f"step {p['angle_step']} deg",
            f"# Int. time        : {self.spectrometer.integration_time_ms} ms",
            f"# Averages         : {self.spectrometer.scans_to_average}",
            f"# Boxcar           : {self.spectrometer.boxcar_width}",
            f"# Dark subtraction : {p.get('subtract_dark', True)}",
            f"# Wavelength range : {wl[0]:.2f} - {wl[-1]:.2f} nm",
            f"# Pixels           : {self.n_pixels}",
            f"#",
            f"# Row layout:",
            f"#  First row       : column names, wavelengths (nm) from col 3",
            f"#  Then per angle  : one 'raw' row and one 'corr' row",
            f"#  Col 0           : actual angle (deg, read back from motor)",
            f"#  Col 1           : nominal angle (deg, requested)",
            f"#  Col 2           : raw | corr (dark-corrected)",
            f"#",
        ]
        with open(self.path_spectrum, "w") as f:
            f.write("\n".join(header_spectrum) + "\n")
            names = ["angle_deg", "nominal_deg", "type"]
            f.write(d.join(names + [f"{w:.4f}" for w in wl]) + "\n")

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
            f"#  Col 0 : Actual angle (deg)",
            f"#  Col 1 : Measured voltage (V)",
            f"#  Col 2 : Measured current (A)",
            f"#  Col 3 : In compliance (0=no 1=yes)",
            f"#  Col 4 : Nominal angle (deg)",
        ]
        col_names_sourcemeter = [
            "angle_deg", "voltage_V", "current_A", "in_compliance",
            "nominal_deg",
        ]
        with open(self.path_sourcemeter, "w") as f:
            f.write("\n".join(header_sourcemeter) + "\n")
            f.write(d.join(col_names_sourcemeter) + "\n")

        log.info("Saving spectra to %s", self.path_spectrum)
        log.info("Saving sourcemeter data to %s", self.path_sourcemeter)
        return self.path_spectrum, self.path_sourcemeter

    def append(self, angle, nominal, volt, curr, comp, raw, corr):
        """Writes one angle to both files and flushes."""
        if len(raw) != self.n_pixels or len(corr) != self.n_pixels:
            raise ValueError(
                f"Spectrum has {len(raw)} pixels, file expects "
                f"{self.n_pixels}")
        d = self.delimiter
        lead = f"{angle:.4f}{d}{nominal:.4f}{d}"

        with open(self.path_spectrum, "a") as f:
            f.write(lead + "raw" + d + d.join(f"{v:.6g}" for v in raw) + "\n")
            f.write(lead + "corr" + d + d.join(f"{v:.6g}" for v in corr) + "\n")

        with open(self.path_sourcemeter, "a") as f:
            f.write(d.join(f"{v:.6g}" for v in
                           [angle, volt, curr, comp, nominal]) + "\n")

    def finish(self, note: str = None):
        """Appends a trailing comment (e.g. why the scan ended early)."""
        if not self.is_open() or not note:
            return
        for path in (self.path_spectrum, self.path_sourcemeter):
            with open(path, "a") as f:
                f.write(f"# Ended: {note}\n")
