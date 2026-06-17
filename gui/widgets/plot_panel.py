"""
Right-panel spectrum plot.

Designed as a single-widget wrapper so that additional plot types
(heatmap, peak-vs-angle, etc.) can be added alongside later.
"""

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class PlotPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (counts)")
        self.ax.set_title("Last Spectrum")
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

    def plot_spectrum(self, angle, wl, counts):
        self.ax.clear()
        self.ax.plot(wl, counts, lw=0.8, color="#2980b9")
        title = (f"Spectrum at {angle:.2f}°"
                 if angle is not None else "Preview Spectrum")
        self.ax.set_title(title)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (counts)")
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()