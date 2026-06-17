"""
gui
───────────────────────────────────────────────────────────────────────
Spectroscopy Angle Scanner — PyQt5 GUI package.

    from gui import MainWindow, load_config
"""

from gui.main_window import MainWindow
from gui.util import load_config

__all__ = ["MainWindow", "load_config"]