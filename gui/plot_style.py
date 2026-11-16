"""
Nature-style matplotlib settings shared by the analysis plots.

Same style as ``scan_analysis.ipynb``: Okabe–Ito palette, sans-serif
5–7 pt text, thin 0.5 pt axes, outward ticks, no top/right spines,
editable-text PDF output.

The style is applied with ``matplotlib.rc_context(nature_rc(...))`` so it
only affects the analysis figures, not the live plot.  ``scale`` enlarges
fonts, lines and ticks together, so the on-screen view stays readable
while exported figures use the exact print sizes (``scale=1``).
"""

import numpy as np
from cycler import cycler

MM = 1 / 25.4
SINGLE, ONE_HALF, DOUBLE = 89 * MM, 120 * MM, 183 * MM   # Nature column widths (in)

# Okabe–Ito colour-blind-safe palette
OI = dict(blue="#0072B2", orange="#E69F00", green="#009E73",
          vermillion="#D55E00", purple="#CC79A7", sky="#56B4E9",
          yellow="#F0E442", black="#000000")

ANGLE_CMAP = "viridis"     # colour = angle
MAP_CMAP   = "magma"       # angle–wavelength intensity map

SCREEN_SCALE = 1.5         # on-screen enlargement of the print sizes


def nature_rc(scale: float = 1.0) -> dict:
    s = scale
    return {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans",
                            "DejaVu Sans"],
        "font.size": 7 * s, "axes.labelsize": 7 * s,
        "axes.titlesize": 7 * s, "figure.titlesize": 7 * s,
        "xtick.labelsize": 6 * s, "ytick.labelsize": 6 * s,
        "legend.fontsize": 6 * s, "legend.title_fontsize": 6 * s,
        "mathtext.default": "regular",
        "axes.linewidth": 0.5 * s,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelpad": 2 * s,
        "axes.prop_cycle": cycler(color=[OI[k] for k in (
            "blue", "vermillion", "green", "orange", "purple", "sky",
            "black")]),
        "lines.linewidth": 0.8 * s, "lines.markersize": 2.5 * s,
        "xtick.direction": "out", "ytick.direction": "out",
        "xtick.major.size": 2.5 * s, "ytick.major.size": 2.5 * s,
        "xtick.minor.size": 1.5 * s, "ytick.minor.size": 1.5 * s,
        "xtick.major.width": 0.5 * s, "ytick.major.width": 0.5 * s,
        "xtick.minor.width": 0.4 * s, "ytick.minor.width": 0.4 * s,
        "xtick.major.pad": 2 * s, "ytick.major.pad": 2 * s,
        "axes.formatter.use_mathtext": True,
        "axes.formatter.limits": (-3, 4),
        "legend.frameon": False, "legend.handlelength": 1.4,
        "legend.borderaxespad": 0.3,
        "image.cmap": ANGLE_CMAP,
        "savefig.dpi": 600, "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    }


def panel_labels(axes, start="a", dx=-14, dy=4, scale=1.0):
    """Bold lower-case panel letters at the top-left outside each axis."""
    for k, ax in enumerate(np.ravel(axes)):
        ax.annotate(chr(ord(start) + k), xy=(0, 1),
                    xycoords="axes fraction",
                    xytext=(dx * scale, dy * scale),
                    textcoords="offset points",
                    fontsize=8 * scale, fontweight="bold",
                    ha="left", va="bottom")


def style_colorbar(cb, label, scale=1.0):
    cb.set_label(label)
    cb.outline.set_linewidth(0.5 * scale)
    cb.ax.tick_params(width=0.5 * scale, length=2 * scale)
    return cb
