"""
Worker-thread → GUI signal bridge.

ScanWorker runs in a background thread and calls plain callbacks.
Those callbacks emit the signals below so that the GUI (main thread)
can safely update widgets.
"""

from PyQt5.QtCore import QObject, pyqtSignal


class ScanBridge(QObject):
    sig_progress = pyqtSignal(int, int, float)        # step, total, angle
    sig_spectrum = pyqtSignal(float, object, object)   # angle, wl, counts
    sig_status   = pyqtSignal(str)
    sig_finished = pyqtSignal(object)                  # (path_spec, path_src) or None
    sig_error    = pyqtSignal(str)