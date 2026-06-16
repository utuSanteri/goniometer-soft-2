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
        fname_src  = f"{filename_sourcemeter}.txt"   # ← was missing in else branch

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
        f"# Column layout:",
        f"#  Col 0          : Angle (deg)",
        f"#  Col 1..{n}      : Raw counts per wavelength pixel",
        f"#  Col {n+1}..{2*n} : Dark-corrected counts per wavelength pixel",
        f"#",
        "# wavelength_nm: " + delimiter.join(f"{w:.4f}" for w in wl),
    ]

    col_names_spectrum = (
        ["angle_deg"] +                      
        [f"raw_{i}"  for i in range(n)] +
        [f"corr_{i}" for i in range(n)]
    )

    with open(full_path_spectrum, "w") as f:
        f.write("\n".join(header_spectrum) + "\n")
        f.write(delimiter.join(col_names_spectrum) + "\n")
        for row in rows:
            angle = row[0]
            raw   = row[4        : 4 + n]
            corr  = row[4 + n    : 4 + 2 * n]
            out   = [angle] + raw + corr
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
        f.write("\n".join(header_sourcemeter) + "\n")   # ← was header_lines (undefined)
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