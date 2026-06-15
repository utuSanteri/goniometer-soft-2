    def _save(self, wavelengths, rows, p) -> str:
        save_dir  = p.get("save_dir", "./data")
        filename_spectrum  = p.get("filename", "scan_data")
        filename_sourcemeter = filename_spectrum + "_sourcemeter-dat"
        delimiter = p.get("delimiter", ";")
        timestamp = p.get("timestamp_in_filename", True)
    
        os.makedirs(save_dir, exist_ok=True)
    
        if timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname1 = f"{filename_spectrum}_{ts}.txt"
            fname2 = f"{filename_sourcemeter}_{ts}.txt"
        else:
            fname1 = f"{filename_spectrum}.txt"
    
        full_path_spectrum = os.path.join(save_dir, fname1)
        full_path_sourcemeter = os.path.join(save_dir, fname2)
    
        wl = wavelengths
        n  = len(wl)
            
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
    
        col_names_spectrum = (
            [f"raw_{i}"  for i in range(n)] +
            [f"corr_{i}" for i in range(n)]
        )

        col_names_sourcemeter = (
            ["angle_deg", "voltage_V", "current_A", "in_compliance"]
        )
    
        with open(full_path_spectrum, "w") as f:
            f.write("\n".join(header_lines) + "\n")
            f.write(delimiter.join(col_names_spectrum) + "\n")

        with open(full_path_sourcemeter, "w") as f:
            f.write("\n".join(header_lines) + "\n")
            f.write(delimiter.join(col_names_sourcemeter) + "\n")
    
        log.info("Data saved to %s", full_path)
        return full_path