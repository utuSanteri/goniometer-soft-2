"""
MainWindow — coordinator that owns the tab bar, right-panel plots,
progress bar, and scan lifecycle.
"""

import logging
import traceback

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QSplitter, QMessageBox,
)
from PyQt5.QtCore import Qt

from gui.state  import HardwareState
from gui.bridge import ScanBridge
from gui.widgets.plot_panel import PlotPanel
from gui.widgets.log_panel  import QTextEditHandler, create_log_panel
from gui.tabs   import (
    ConnectTab, SpectrometerTab, SourceTab, ScanTab, ManualTab,
)
from scan_worker import ScanWorker

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self, config: dict):
        super().__init__()
        self.cfg    = config
        self.hw     = HardwareState()
        self.bridge = ScanBridge()
        self.worker = None

        self.setWindowTitle("Spectroscopy Angle Scanner")
        self.resize(1200, 800)
        self._build_ui()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────────────
    #  UI construction
    # ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ── Left panel: tabs ──────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(400)
        left.setMaximumWidth(480)
        left_layout = QVBoxLayout(left)

        self.tabs = QTabWidget()

        self.tab_connect = ConnectTab(self.hw, self.cfg)
        self.tab_spec    = SpectrometerTab(self.hw, self.cfg)
        self.tab_source  = SourceTab(self.hw, self.cfg)
        self.tab_scan    = ScanTab(self.cfg)
        self.tab_manual  = ManualTab(
            self.hw, self.cfg,
            get_subtract_dark=lambda: self.tab_spec.subtract_dark,
        )

        self.tabs.addTab(self.tab_connect, "Connect")
        self.tabs.addTab(self.tab_spec,    "Spectrometer")
        self.tabs.addTab(self.tab_source,  "Source")
        self.tabs.addTab(self.tab_scan,    "Scan")
        self.tabs.addTab(self.tab_manual,  "Manual")

        left_layout.addWidget(self.tabs)

        # Progress bar + status label
        bot = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.lbl_status = QLabel("Idle")
        bot.addWidget(self.progress)
        bot.addWidget(self.lbl_status)
        left_layout.addLayout(bot)

        splitter.addWidget(left)

        # ── Right panel: plot + log ───────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.plot_panel = PlotPanel()
        right_layout.addWidget(self.plot_panel, stretch=3)

        self.log_box = create_log_panel()
        right_layout.addWidget(self.log_box, stretch=1)

        splitter.addWidget(right)

        # Logging handler → root logger
        handler = QTextEditHandler(self.log_box)
        handler.setFormatter(
            logging.Formatter("%(levelname)s │ %(message)s"))
        logging.getLogger().addHandler(handler)

    # ─────────────────────────────────────────────────────────────────
    #  Signal wiring
    # ─────────────────────────────────────────────────────────────────
    def _connect_signals(self):
        # Plot requests from tabs
        self.tab_spec.sig_plot.connect(self.plot_panel.plot_spectrum)
        self.tab_manual.sig_plot.connect(self.plot_panel.plot_spectrum)

        # Scan lifecycle
        self.tab_scan.sig_start_requested.connect(self._start_scan)
        self.tab_scan.sig_stop_requested.connect(self._stop_scan)

        # Bridge (worker thread → main thread)
        self.bridge.sig_progress.connect(self._on_progress)
        self.bridge.sig_spectrum.connect(self.plot_panel.plot_spectrum)
        self.bridge.sig_status.connect(self._on_status)
        self.bridge.sig_finished.connect(self._on_finished)
        self.bridge.sig_error.connect(self._on_error)

    # ─────────────────────────────────────────────────────────────────
    #  Scan control
    # ─────────────────────────────────────────────────────────────────
    def _start_scan(self):
        if not self.hw.motor:
            QMessageBox.critical(self, "Error", "Motor not connected")
            return
        if not self.hw.spec:
            QMessageBox.critical(
                self, "Error", "Spectrometer not connected")
            return
        if not self.hw.source:
            QMessageBox.critical(
                self, "Error", "Source meter not connected")
            return

        self.tab_spec.apply_settings()
        self.tab_source.apply_settings()

        params = self.tab_scan.get_params()
        params["subtract_dark"] = self.tab_spec.subtract_dark

        bridge = self.bridge
        callbacks = {
            "on_progress": lambda s, t, a:
                bridge.sig_progress.emit(s, t, a),
            "on_spectrum": lambda a, w, c:
                bridge.sig_spectrum.emit(a, w, c),
            "on_status": lambda m:
                bridge.sig_status.emit(m),
            "on_finished": lambda p:
                bridge.sig_finished.emit(p),
            "on_error": lambda e:
                bridge.sig_error.emit(traceback.format_exc()),
        }

        self.worker = ScanWorker(
            self.hw.motor, self.hw.spec, self.hw.source,
            params, callbacks,
        )
        self.worker.start()
        self.tab_scan.set_running(True)
        self.progress.setValue(0)
        log.info("Scan started")

    def _stop_scan(self):
        if self.worker:
            self.worker.stop()
        self.tab_scan.set_running(False)

    # ─────────────────────────────────────────────────────────────────
    #  Bridge slots
    # ─────────────────────────────────────────────────────────────────
    def _on_progress(self, step: int, total: int, angle: float):
        pct = int(100 * step / total)
        self.progress.setValue(pct)
        self.lbl_status.setText(
            f"Step {step}/{total} — {angle:.2f}°")

    def _on_status(self, msg: str):
        self.lbl_status.setText(msg[:80])

    def _on_finished(self, paths):
        self.tab_scan.set_running(False)
        self.progress.setValue(100)

        if paths:
            path_spec, path_src = paths
            QMessageBox.information(
                self, "Scan Complete",
                f"Data saved:\n\n"
                f"Spectra:\n  {path_spec}\n\n"
                f"Sourcemeter:\n  {path_src}",
            )
        else:
            self.lbl_status.setText("Scan stopped")

    def _on_error(self, tb: str):
        self.tab_scan.set_running(False)
        QMessageBox.critical(self, "Scan Error", tb)
        log.error("Scan error:\n%s", tb)

    # ─────────────────────────────────────────────────────────────────
    #  Shutdown
    # ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self.worker and self.worker.is_running():
            self.worker.stop()
        if self.hw.motor:
            self.hw.motor.disconnect()
        if self.hw.spec:
            self.hw.spec.disconnect()
        if self.hw.source:
            self.hw.source.disconnect()
        event.accept()