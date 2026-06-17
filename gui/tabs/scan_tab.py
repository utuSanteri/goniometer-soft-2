import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QFileDialog,
)
from PyQt5.QtCore import pyqtSignal

log = logging.getLogger(__name__)


class ScanTab(QWidget):
    """Scan parameters, file settings, start / stop."""

    sig_start_requested = pyqtSignal()
    sig_stop_requested  = pyqtSignal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        grp = QGroupBox("Angle Scan Parameters")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Start angle (°):"), 0, 0)
        self.spn_ang_start = QDoubleSpinBox()
        self.spn_ang_start.setRange(-720, 720)
        self.spn_ang_start.setValue(
            self.cfg["scan"]["angle_start_deg"])
        g.addWidget(self.spn_ang_start, 0, 1)

        g.addWidget(QLabel("End angle (°):"), 1, 0)
        self.spn_ang_end = QDoubleSpinBox()
        self.spn_ang_end.setRange(-720, 720)
        self.spn_ang_end.setValue(
            self.cfg["scan"]["angle_end_deg"])
        g.addWidget(self.spn_ang_end, 1, 1)

        g.addWidget(QLabel("Step (°/spectrum):"), 2, 0)
        self.spn_ang_step = QDoubleSpinBox()
        self.spn_ang_step.setRange(0.01, 360)
        self.spn_ang_step.setValue(
            self.cfg["scan"]["angle_step_deg"])
        g.addWidget(self.spn_ang_step, 2, 1)

        g.addWidget(QLabel("Motor #:"), 3, 0)
        self.cmb_motor_id = QComboBox()
        self.cmb_motor_id.addItems(["1", "2"])
        g.addWidget(self.cmb_motor_id, 3, 1)
        lay.addWidget(grp)

        # ── Save Settings ────────────────────────────────────────────
        grp2 = QGroupBox("Save Settings")
        g2 = QGridLayout(grp2)

        g2.addWidget(QLabel("Filename:"), 0, 0)
        self.inp_filename = QLineEdit(
            self.cfg["data"]["default_filename"])
        g2.addWidget(self.inp_filename, 0, 1)

        g2.addWidget(QLabel("Save directory:"), 1, 0)
        self.inp_savedir = QLineEdit(
            self.cfg["data"]["default_save_dir"])
        g2.addWidget(self.inp_savedir, 1, 1)

        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse_dir)
        g2.addWidget(self.btn_browse, 2, 0, 1, 2)

        self.chk_timestamp = QCheckBox(
            "Append timestamp to filename")
        self.chk_timestamp.setChecked(
            self.cfg["data"]["timestamp_in_filename"])
        g2.addWidget(self.chk_timestamp, 3, 0, 1, 2)
        lay.addWidget(grp2)

        # ── Run ──────────────────────────────────────────────────────
        grp3 = QGroupBox("Run")
        g3 = QVBoxLayout(grp3)
        self.btn_start = QPushButton("▶  Start Scan")
        self.btn_start.setStyleSheet(
            "background-color: #3498db; color: white; "
            "font-size: 14px; font-weight: bold; padding: 8px")
        self.btn_start.clicked.connect(self.sig_start_requested)
        self.btn_stop = QPushButton("■  Stop Scan")
        self.btn_stop.setStyleSheet(
            "background-color: #e74c3c; color: white; "
            "font-size: 14px; font-weight: bold; padding: 8px")
        self.btn_stop.clicked.connect(self.sig_stop_requested)
        self.btn_stop.setEnabled(False)
        g3.addWidget(self.btn_start)
        g3.addWidget(self.btn_stop)
        lay.addWidget(grp3)

        lay.addStretch()

    # ── Public API ────────────────────────────────────────────────────
    def get_params(self) -> dict:
        """Gather current scan parameter values from the UI."""
        return {
            "angle_start":          self.spn_ang_start.value(),
            "angle_end":            self.spn_ang_end.value(),
            "angle_step":           self.spn_ang_step.value(),
            "motor_id":             int(self.cmb_motor_id.currentText()),
            "filename":             self.inp_filename.text(),
            "save_dir":             self.inp_savedir.text(),
            "timestamp_in_filename": self.chk_timestamp.isChecked(),
            "delimiter":            self.cfg["data"]["delimiter"],
        }

    def set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    # ── Private ───────────────────────────────────────────────────────
    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", self.inp_savedir.text())
        if d:
            self.inp_savedir.setText(d)