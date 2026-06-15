"""
plot_scan.py
────────────────────────────────────────────────────────────────────────
Standalone plotter for spectroscopy scan data files.

Usage:
  python plot_scan.py                    # opens file picker
  python plot_scan.py path/to/file.txt   # direct file argument
  python plot_scan.py --raw              # plot raw counts
"""

import sys
import os
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.cm as cm
from matplotlib.gridspec import GridSpec
from tkinter import Tk, filedialog


# ══════════════════════════════════════════════════════════════════════
#  File loader
# ══════════════════════════════════════════════════════════════════════
def load_scan_file(path: str) -> dict:
    meta        = {}
    wavelengths = None
    col_names   = None
    data_rows   = []

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")

            if line.startswith("#"):
                content = line[1:].strip()

                if content.startswith("wavelength_nm:"):
                    wl_str = content.split(":", 1)[1].strip()
                    wavelengths = np.array([float(w) for w in wl_str.split("\t")
                                            if w.strip()])
                    continue

                if ":" in content and not content.startswith("Col"):
                    k, v = content.split(":", 1)
                    meta[k.strip()] = v.strip()
                continue

            if col_names is None:
                col_names = line.split("\t")
                continue

            if line.strip():
                data_rows.append([float(x) for x in line.split("\t")])

    if not data_rows:
        raise ValueError("No data rows found in file.")
    if wavelengths is None:
        raise ValueError("Could not find wavelength row in file header.")

    data = np.array(data_rows)

    # Layout: angle, voltage, current, compliance, raw×N, corr×N
    n_data_cols = data.shape[1]
    n_wl_data   = (n_data_cols - 4) // 2
    n_wl        = min(len(wavelengths), n_wl_data)

    if len(wavelengths) != n_wl_data:
        print(f"  Note: wavelength header has {len(wavelengths)} pixels, "
              f"data has {n_wl_data} — trimming both to {n_wl}")

    wavelengths = wavelengths[:n_wl]
    angles      = data[:, 0]
    voltages    = data[:, 1]
    currents    = data[:, 2]
    compliance  = data[:, 3].astype(bool)
    raw         = data[:, 4        : 4 + n_wl]
    corr        = data[:, 4 + n_wl : 4 + 2 * n_wl]

    return {
        "path"       : path,
        "meta"       : meta,
        "wavelengths": wavelengths,
        "angles"     : angles,
        "voltages"   : voltages,
        "currents"   : currents,
        "compliance" : compliance,
        "raw"        : raw,
        "corrected"  : corr,
    }


# ══════════════════════════════════════════════════════════════════════
#  Plots
# ══════════════════════════════════════════════════════════════════════
def plot_all(d: dict, use_corrected: bool = True):

    spectra    = d["corrected"] if use_corrected else d["raw"]
    wl         = d["wavelengths"]
    angles     = d["angles"]
    fname      = os.path.basename(d["path"])
    n_angles   = len(angles)
    spec_label = "Dark-corrected counts" if use_corrected else "Raw counts"

    # One colour per angle
    cmap    = matplotlib.colormaps["plasma"].resampled(n_angles)
    colours = [cmap(i) for i in range(n_angles)]

    # ── Figure 1: Waterfall ───────────────────────────────────────────
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    for i, (angle, spectrum) in enumerate(zip(angles, spectra)):
        ax1.plot(wl, spectrum, color=colours[i],
                 lw=0.9, alpha=0.85, label=f"{angle:.1f}°")

    ax1.set_xlabel("Wavelength (nm)", fontsize=12)
    ax1.set_ylabel(spec_label, fontsize=12)
    ax1.set_title(f"All spectra — {fname}", fontsize=12)
    ax1.grid(True, alpha=0.25)

    # ── colourbar fix: cm.ScalarMappable not matplotlib.ScalarMappable
    sm = cm.ScalarMappable(
        cmap="plasma",
        norm=plt.Normalize(angles.min(), angles.max()))
    sm.set_array([])
    cbar = fig1.colorbar(sm, ax=ax1)
    cbar.set_label("Angle (°)", fontsize=11)
    fig1.tight_layout()

    # ── Figure 2: 2-D intensity map ───────────────────────────────────
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    extent = [wl[0], wl[-1], angles[-1], angles[0]]
    im = ax2.imshow(spectra, aspect="auto", extent=extent,
                    cmap="inferno", origin="upper")
    ax2.set_xlabel("Wavelength (nm)", fontsize=12)
    ax2.set_ylabel("Angle (°)", fontsize=12)
    ax2.set_title(f"Intensity map — {fname}", fontsize=12)
    cbar2 = fig2.colorbar(im, ax=ax2)
    cbar2.set_label(spec_label, fontsize=11)
    fig2.tight_layout()

    # ── Figure 3: Integrated intensity vs angle ───────────────────────
    integrated = spectra.sum(axis=1)

    fig3, ax3 = plt.subplots(figsize=(8, 4))
    ax3.plot(angles, integrated, "o-", color="#2980b9",
             lw=1.5, ms=5, label="Integrated intensity")

    comp_angles = angles[d["compliance"]]
    comp_int    = integrated[d["compliance"]]
    if len(comp_angles):
        ax3.scatter(comp_angles, comp_int, color="red", zorder=5,
                    label="In compliance ⚠", s=60, marker="x")

    ax3.set_xlabel("Angle (°)", fontsize=12)
    ax3.set_ylabel("Integrated counts", fontsize=12)
    ax3.set_title(f"Integrated intensity vs angle — {fname}", fontsize=12)
    ax3.legend()
    ax3.grid(True, alpha=0.25)
    fig3.tight_layout()

    # ── Figure 4: Electrical readback ─────────────────────────────────
    fig4, (ax4a, ax4b) = plt.subplots(2, 1, figsize=(8, 5), sharex=True)

    ax4a.plot(angles, d["voltages"], "s-", color="#27ae60",
              lw=1.5, ms=4, label="Voltage (V)")
    ax4a.set_ylabel("Voltage (V)", fontsize=11)
    ax4a.grid(True, alpha=0.25)
    ax4a.legend(loc="upper right")

    ax4b.plot(angles, d["currents"] * 1e3, "s-", color="#c09066",
              lw=1.5, ms=4, label="Current (mA)")
    ax4b.set_ylabel("Current (mA)", fontsize=11)
    ax4b.set_xlabel("Angle (°)", fontsize=12)
    ax4b.grid(True, alpha=0.25)
    ax4b.legend(loc="upper right")

    for ax in (ax4a, ax4b):
        for i, comp in enumerate(d["compliance"]):
            if comp:
                ax.axvline(angles[i], color="red", alpha=0.4, lw=1.5, ls="--")

    if d["compliance"].any():
        ax4a.plot([], [], color="red", alpha=0.6,
                  lw=1.5, ls="--", label="Compliance ⚠")
        ax4a.legend(loc="upper right")

    fig4.suptitle(f"Electrical readback — {fname}", fontsize=12)
    fig4.tight_layout()

    # ── Figure 5: Interactive spectrum picker ─────────────────────────
    _interactive_spectrum_picker(wl, spectra, angles, colours,
                                 spec_label, fname)

    plt.show()


def _interactive_spectrum_picker(wl, spectra, angles, colours,
                                 spec_label, fname):
    fig5 = plt.figure(figsize=(12, 5))
    gs   = GridSpec(1, 2, figure=fig5, width_ratios=[1, 2])
    ax_l = fig5.add_subplot(gs[0])
    ax_r = fig5.add_subplot(gs[1])

    integrated = spectra.sum(axis=1)

    bar_height = (np.diff(angles).min() * 0.8
                  if len(angles) > 1 else 1.0)
    bar_height = max(0.4, bar_height)

    ax_l.barh(angles, integrated,
              color=colours, height=bar_height, align="center")
    ax_l.set_xlabel("Integrated counts", fontsize=10)
    ax_l.set_ylabel("Angle (°)", fontsize=10)
    ax_l.set_title("Click an angle →", fontsize=10)
    ax_l.invert_yaxis()
    ax_l.grid(True, alpha=0.2, axis="x")

    [line] = ax_r.plot(wl, spectra[0], color=colours[0], lw=1.0)
    ax_r.set_xlabel("Wavelength (nm)", fontsize=11)
    ax_r.set_ylabel(spec_label, fontsize=11)
    ax_r.set_title(f"{fname}  |  angle = {angles[0]:.2f}°", fontsize=10)
    ax_r.grid(True, alpha=0.25)

    highlight = [ax_l.axhline(angles[0], color="white",
                               lw=1.5, ls="--", alpha=0.8)]

    def on_click(event):
        if event.inaxes != ax_l or event.ydata is None:
            return
        idx = int(np.argmin(np.abs(angles - event.ydata)))
        line.set_ydata(spectra[idx])
        line.set_color(colours[idx])
        ax_r.set_title(f"{fname}  |  angle = {angles[idx]:.2f}°",
                       fontsize=10)
        ax_r.relim()
        ax_r.autoscale_view()
        highlight[0].remove()
        highlight[0] = ax_l.axhline(angles[idx], color="white",
                                     lw=1.5, ls="--", alpha=0.8)
        fig5.canvas.draw_idle()

    fig5.canvas.mpl_connect("button_press_event", on_click)
    fig5.suptitle("Spectrum Inspector  (click angle bar to view)",
                  fontsize=11)
    fig5.tight_layout()


# ══════════════════════════════════════════════════════════════════════
#  Summary printer
# ══════════════════════════════════════════════════════════════════════
def print_summary(d: dict):
    peak_idx   = np.unravel_index(d["corrected"].argmax(),
                                   d["corrected"].shape)
    peak_wl    = d["wavelengths"][peak_idx[1]]
    peak_count = d["corrected"].max()

    print("\n" + "═" * 55)
    print(f"  File      : {os.path.basename(d['path'])}")
    print("─" * 55)
    for k, v in d["meta"].items():
        print(f"  {k:<20}: {v}")
    print("─" * 55)
    print(f"  Angles    : {len(d['angles'])}  "
          f"({d['angles'][0]:.2f}° → {d['angles'][-1]:.2f}°)")
    print(f"  Pixels    : {len(d['wavelengths'])}  "
          f"({d['wavelengths'][0]:.1f} – {d['wavelengths'][-1]:.1f} nm)")
    print(f"  Compliance: "
          f"{d['compliance'].sum()} / {len(d['compliance'])} steps hit limit")
    print(f"  Peak count: {peak_count:.1f}  @ {peak_wl:.2f} nm")
    print("═" * 55 + "\n")


# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════
def pick_file() -> str:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Select scan data file",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    root.destroy()
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Plot spectroscopy scan output data")
    parser.add_argument("file", nargs="?", default=None,
                        help="Path to scan data .txt file")
    parser.add_argument("--raw", action="store_true",
                        help="Plot raw counts instead of dark-corrected")
    args = parser.parse_args()

    path = args.file
    if not path:
        path = pick_file()
    if not path:
        print("No file selected.")
        sys.exit(0)
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Loading: {path}")
    data = load_scan_file(path)
    print_summary(data)
    plot_all(data, use_corrected=not args.raw)


if __name__ == "__main__":
    main()