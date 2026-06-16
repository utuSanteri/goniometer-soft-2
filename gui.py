"""
gui.py
───────────────────────────────────────────────────────────────────────
Main GUI — PyQt5
Run:  python gui.py <- this is the "main program" for the goniometer software
"""

import sys
import os
import logging
import traceback
from functools import partial

import yaml
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QTextEdit, QFileDialog,
    QProgressBar, QSplitter, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QColor

# Matplotlib embedded
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Custom module imports------------------------------------------------------------
# ── Real hardware ──────────────────────────────────────────────────
#from hardware import MotorController, Spectrometer, SourceMeter, SourceMeterError

# Fake hardware for testing
from hardware_mock import MotorController, Spectrometer, SourceMeter, SourceMeterError

from scan_worker import ScanWorker



# ── Logging to GUI ────────────────────────────────────────────────────
log = logging.getLogger()
log.setLevel(logging.DEBUG)


class QTextEditHandler(logging.Handler):
    def __init__(self, widget: QTextEdit):
        super().__init__()
        self._w = widget

    def emit(self, record):
        msg = self.format(record)
        # Always append in main thread
        self._w.append(msg)
        self._w.verticalScrollBar().setValue(
            self._w.verticalScrollBar().maximum())


# ══════════════════════════════════════════════════════════════════════
#  Bridge: worker-thread → GUI (Qt signals)
# ══════════════════════════════════════════════════════════════════════
class ScanBridge(QObject):
    sig_progress = pyqtSignal(int, int, float)          # step, total, angle
    sig_spectrum = pyqtSignal(float, object, object)    # angle, wl, counts
    sig_status   = pyqtSignal(str)
    sig_finished = pyqtSignal(object)                   # path or None
    sig_error    = pyqtSignal(str)


# ══════════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):

    def __init__(self, config: dict):
        super().__init__()
        self.cfg = config
        self.motor = None
        self.spec   = None
        self.source = None
        self.worker = None
        self.bridge = ScanBridge()
        self._connect_bridge()

        self.setWindowTitle("Spectroscopy Angle Scanner")
        self.resize(1200, 800)
        self._build_ui()

    # ── Bridge signals → GUI slots ────────────────────────────────────
    def _connect_bridge(self):
        self.bridge.sig_progress.connect(self._on_progress)
        self.bridge.sig_spectrum.connect(self._on_spectrum)
        self.bridge.sig_status.connect(self._on_status)
        self.bridge.sig_finished.connect(self._on_finished)
        self.bridge.sig_error.connect(self._on_error)

    # ─────────────────────────────────────────────────────────────────
    #  UI Construction
    # ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # Left panel: controls
        left = QWidget()
        left.setMinimumWidth(400)
        left.setMaximumWidth(480)
        left_layout = QVBoxLayout(left)
        self.tabs = QTabWidget()
        left_layout.addWidget(self.tabs)

        self.tabs.addTab(self._tab_connect(),     "Connect")
        self.tabs.addTab(self._tab_spectrometer(), "Spectrometer")
        self.tabs.addTab(self._tab_source(),       "Source")
        self.tabs.addTab(self._tab_scan(),         "Scan")
        self.tabs.addTab(self._tab_manual(),       "Manual")

        splitter.addWidget(left)

        # Right panel: plot + log
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.fig = Figure(figsize=(6, 4))
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (counts)")
        self.ax.set_title("Last Spectrum")
        self.canvas = FigureCanvas(self.fig)
        right_layout.addWidget(self.canvas, stretch=3)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Courier", 8))
        self.log_box.setMaximumHeight(180)
        right_layout.addWidget(self.log_box, stretch=1)

        splitter.addWidget(right)

        # Logging handler
        handler = QTextEditHandler(self.log_box)
        handler.setFormatter(logging.Formatter("%(levelname)s │ %(message)s"))
        log.addHandler(handler)

        # Progress bar + status
        bot = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.lbl_status = QLabel("Idle")
        bot.addWidget(self.progress)
        bot.addWidget(self.lbl_status)
        left_layout.addLayout(bot)

    # ── Tab: Connect ──────────────────────────────────────────────────
    def _tab_connect(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        # Motor
        grp = QGroupBox("Motor Controller (Arduino)")
        g = QGridLayout(grp)
        g.addWidget(QLabel("Serial Port:"), 0, 0)
        self.inp_motor_port = QLineEdit(self.cfg["motors"]["port"])
        g.addWidget(self.inp_motor_port, 0, 1)
        g.addWidget(QLabel("Baud:"), 1, 0)
        self.inp_motor_baud = QLineEdit(str(self.cfg["motors"]["baud"]))
        g.addWidget(self.inp_motor_baud, 1, 1)
        self.btn_motor_connect = QPushButton("Connect Motor")
        self.btn_motor_connect.clicked.connect(self._connect_motor)
        g.addWidget(self.btn_motor_connect, 2, 0, 1, 2)
        self.lbl_motor_status = QLabel("● Disconnected")
        self.lbl_motor_status.setStyleSheet("color: red")
        g.addWidget(self.lbl_motor_status, 3, 0, 1, 2)
        lay.addWidget(grp)

        # Spectrometer
        grp2 = QGroupBox("Spectrometer (OceanOptics)")
        g2 = QGridLayout(grp2)
        self.btn_spec_connect = QPushButton("Connect Spectrometer")
        self.btn_spec_connect.clicked.connect(self._connect_spec)
        g2.addWidget(self.btn_spec_connect, 0, 0, 1, 2)
        self.lbl_spec_status = QLabel("● Disconnected")
        self.lbl_spec_status.setStyleSheet("color: red")
        g2.addWidget(self.lbl_spec_status, 1, 0, 1, 2)
        lay.addWidget(grp2)

        # Source meter
        grp3 = QGroupBox("Source Meter (Keithley 2461)")
        g3 = QGridLayout(grp3)
        g3.addWidget(QLabel("VISA Resource:"), 0, 0)
        self.inp_visa = QLineEdit(self.cfg["sourcemeter"]["visa_resource"])
        g3.addWidget(self.inp_visa, 0, 1)
        self.btn_src_connect = QPushButton("Connect Source Meter")
        self.btn_src_connect.clicked.connect(self._connect_source)
        g3.addWidget(self.btn_src_connect, 1, 0, 1, 2)
        self.lbl_src_status = QLabel("● Disconnected")
        self.lbl_src_status.setStyleSheet("color: red")
        g3.addWidget(self.lbl_src_status, 2, 0, 1, 2)
        lay.addWidget(grp3)

        lay.addStretch()
        return w

    # ── Tab: Spectrometer ─────────────────────────────────────────────
    def _tab_spectrometer(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        grp = QGroupBox("Acquisition Settings")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Integration time (ms):"), 0, 0)
        self.spn_inttime = QDoubleSpinBox()
        self.spn_inttime.setRange(1, 60000)
        self.spn_inttime.setValue(
            self.cfg["spectrometer"]["default_integration_time_ms"])
        self.spn_inttime.valueChanged.connect(self._apply_spec_settings)
        g.addWidget(self.spn_inttime, 0, 1)

        g.addWidget(QLabel("Scans to average:"), 1, 0)
        self.spn_avg = QSpinBox()
        self.spn_avg.setRange(1, 100)
        self.spn_avg.setValue(
            self.cfg["spectrometer"]["default_scans_to_average"])
        self.spn_avg.valueChanged.connect(self._apply_spec_settings)
        g.addWidget(self.spn_avg, 1, 1)

        g.addWidget(QLabel("Boxcar width:"), 2, 0)
        self.spn_boxcar = QSpinBox()
        self.spn_boxcar.setRange(0, 20)
        self.spn_boxcar.setValue(
            self.cfg["spectrometer"]["default_boxcar_width"])
        self.spn_boxcar.valueChanged.connect(self._apply_spec_settings)
        g.addWidget(self.spn_boxcar, 2, 1)

        self.chk_dark = QCheckBox("Subtract dark spectrum")
        self.chk_dark.setChecked(True)
        g.addWidget(self.chk_dark, 3, 0, 1, 2)
        lay.addWidget(grp)

        grp2 = QGroupBox("Dark Spectrum")
        g2 = QVBoxLayout(grp2)
        self.btn_collect_dark = QPushButton("Collect Dark Now")
        self.btn_collect_dark.clicked.connect(self._collect_dark)
        g2.addWidget(self.btn_collect_dark)
        self.btn_clear_dark = QPushButton("Clear Dark")
        self.btn_clear_dark.clicked.connect(self._clear_dark)
        g2.addWidget(self.btn_clear_dark)
        self.lbl_dark_status = QLabel("No dark spectrum")
        g2.addWidget(self.lbl_dark_status)
        lay.addWidget(grp2)

        # Live preview
        grp3 = QGroupBox("Preview")
        g3 = QVBoxLayout(grp3)
        self.btn_preview = QPushButton("Acquire Preview Spectrum")
        self.btn_preview.clicked.connect(self._preview_spectrum)
        g3.addWidget(self.btn_preview)
        lay.addWidget(grp3)

        lay.addStretch()
        return w

    # ── Tab: Source ───────────────────────────────────────────────────
    def _tab_source(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        # ── Source Settings ───────────────────────────────────────────────
        grp = QGroupBox("Source Settings")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Source mode:"), 0, 0)
        self.cmb_source_mode = QComboBox()
        self.cmb_source_mode.addItems(["VOLT", "CURR"])
        self.cmb_source_mode.setCurrentText(
            self.cfg["sourcemeter"]["source_mode"])
        g.addWidget(self.cmb_source_mode, 0, 1)

        g.addWidget(QLabel("Voltage (V):"), 1, 0)
        self.spn_voltage = QDoubleSpinBox()
        self.spn_voltage.setRange(0, 100)
        self.spn_voltage.setDecimals(3)
        self.spn_voltage.setValue(self.cfg["sourcemeter"]["default_voltage_v"])
        g.addWidget(self.spn_voltage, 1, 1)

        g.addWidget(QLabel("Current limit (A):"), 2, 0)
        self.spn_current = QDoubleSpinBox()
        self.spn_current.setRange(0, 1.05)
        self.spn_current.setDecimals(4)
        self.spn_current.setValue(
            self.cfg["sourcemeter"]["default_current_limit_a"])
        g.addWidget(self.spn_current, 2, 1)

        g.addWidget(QLabel("Settle time (ms):"), 3, 0)
        self.spn_settle = QDoubleSpinBox()
        self.spn_settle.setRange(0, 5000)
        self.spn_settle.setValue(self.cfg["sourcemeter"]["settle_time_ms"])
        g.addWidget(self.spn_settle, 3, 1)

        self.btn_apply_src = QPushButton("Apply Settings")
        self.btn_apply_src.clicked.connect(self._apply_source_settings)
        g.addWidget(self.btn_apply_src, 4, 0, 1, 2)
        lay.addWidget(grp)

        # ── Verification Settings ─────────────────────────────────────────
        grp_ver = QGroupBox("Verification Settings")
        gv = QGridLayout(grp_ver)

        # Enable / disable automatic verification on output_on()
        self.chk_verify = QCheckBox("Verify on Output ON")
        self.chk_verify.setChecked(
            self.cfg["sourcemeter"].get("verify_on_output_on", True))
        self.chk_verify.setToolTip(
            "When checked, measured signal and compliance are checked "
            "automatically after Output ON.")
        gv.addWidget(self.chk_verify, 0, 0, 1, 2)

        gv.addWidget(QLabel("Current threshold (A):"), 1, 0)
        self.spn_curr_thresh = QDoubleSpinBox()
        self.spn_curr_thresh.setRange(0.0, 1.05)
        self.spn_curr_thresh.setDecimals(9)
        self.spn_curr_thresh.setSingleStep(1e-6)
        self.spn_curr_thresh.setValue(
            self.cfg["sourcemeter"].get("current_threshold_a", 1e-6))
        self.spn_curr_thresh.setToolTip(
            "Minimum expected current (VOLT mode).  "
            "A measurement below this raises a signal-absent error.")
        gv.addWidget(self.spn_curr_thresh, 1, 1)

        gv.addWidget(QLabel("Voltage threshold (V):"), 2, 0)
        self.spn_volt_thresh = QDoubleSpinBox()
        self.spn_volt_thresh.setRange(0.0, 100.0)
        self.spn_volt_thresh.setDecimals(6)
        self.spn_volt_thresh.setSingleStep(1e-3)
        self.spn_volt_thresh.setValue(
            self.cfg["sourcemeter"].get("voltage_threshold_v", 1e-3))
        self.spn_volt_thresh.setToolTip(
            "Minimum expected voltage (CURR mode).  "
            "A measurement below this raises a signal-absent error.")
        gv.addWidget(self.spn_volt_thresh, 2, 1)

        gv.addWidget(QLabel("Compliance fraction:"), 3, 0)
        self.spn_comp_frac = QDoubleSpinBox()
        self.spn_comp_frac.setRange(0.50, 1.00)
        self.spn_comp_frac.setDecimals(2)
        self.spn_comp_frac.setSingleStep(0.01)
        self.spn_comp_frac.setValue(
            self.cfg["sourcemeter"].get("compliance_fraction", 0.95))
        self.spn_comp_frac.setToolTip(
            "Fraction of the configured limit at which the source is "
            "considered to be saturating / in compliance (e.g. 0.95 = 95%).")
        gv.addWidget(self.spn_comp_frac, 3, 1)

        lay.addWidget(grp_ver)

        # ── Manual Output Control ─────────────────────────────────────────
        grp2 = QGroupBox("Manual Output Control")
        g2 = QHBoxLayout(grp2)
        self.btn_out_on = QPushButton("Output ON")
        self.btn_out_on.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold")
        self.btn_out_on.clicked.connect(self._output_on)
        self.btn_out_off = QPushButton("Output OFF")
        self.btn_out_off.setStyleSheet(
            "background-color: #e74c3c; color: white; font-weight: bold")
        self.btn_out_off.clicked.connect(self._output_off)
        g2.addWidget(self.btn_out_on)
        g2.addWidget(self.btn_out_off)
        lay.addWidget(grp2)

        # ── Measurement ───────────────────────────────────────────────────
        grp3 = QGroupBox("Measurement")
        g3 = QVBoxLayout(grp3)
        self.btn_measure = QPushButton("Read Measurement")
        self.btn_measure.clicked.connect(self._manual_measure)
        g3.addWidget(self.btn_measure)
        self.lbl_measure = QLabel("—")
        self.lbl_measure.setFont(QFont("Courier", 14))
        g3.addWidget(self.lbl_measure)

        # Compliance / verification status indicator
        self.lbl_verify_status = QLabel("")
        self.lbl_verify_status.setFont(QFont("Courier", 10))
        self.lbl_verify_status.setWordWrap(True)
        g3.addWidget(self.lbl_verify_status)

        lay.addWidget(grp3)
        lay.addStretch()
        return w

    # ── Tab: Scan ─────────────────────────────────────────────────────
    def _tab_scan(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        grp = QGroupBox("Angle Scan Parameters")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Start angle (°):"), 0, 0)
        self.spn_ang_start = QDoubleSpinBox()
        self.spn_ang_start.setRange(-720, 720)
        self.spn_ang_start.setValue(self.cfg["scan"]["angle_start_deg"])
        g.addWidget(self.spn_ang_start, 0, 1)

        g.addWidget(QLabel("End angle (°):"), 1, 0)
        self.spn_ang_end = QDoubleSpinBox()
        self.spn_ang_end.setRange(-720, 720)
        self.spn_ang_end.setValue(self.cfg["scan"]["angle_end_deg"])
        g.addWidget(self.spn_ang_end, 1, 1)

        g.addWidget(QLabel("Step (°/spectrum):"), 2, 0)
        self.spn_ang_step = QDoubleSpinBox()
        self.spn_ang_step.setRange(0.01, 360)
        self.spn_ang_step.setValue(self.cfg["scan"]["angle_step_deg"])
        g.addWidget(self.spn_ang_step, 2, 1)

        g.addWidget(QLabel("Motor #:"), 3, 0)
        self.cmb_motor_id = QComboBox()
        self.cmb_motor_id.addItems(["1", "2"])
        g.addWidget(self.cmb_motor_id, 3, 1)
        lay.addWidget(grp)

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

        self.chk_timestamp = QCheckBox("Append timestamp to filename")
        self.chk_timestamp.setChecked(
            self.cfg["data"]["timestamp_in_filename"])
        g2.addWidget(self.chk_timestamp, 3, 0, 1, 2)
        lay.addWidget(grp2)

        grp3 = QGroupBox("Run")
        g3 = QVBoxLayout(grp3)
        self.btn_start = QPushButton("▶  Start Scan")
        self.btn_start.setStyleSheet(
            "background-color: #3498db; color: white; "
            "font-size: 14px; font-weight: bold; padding: 8px")
        self.btn_start.clicked.connect(self._start_scan)
        self.btn_stop = QPushButton("■  Stop Scan")
        self.btn_stop.setStyleSheet(
            "background-color: #e74c3c; color: white; "
            "font-size: 14px; font-weight: bold; padding: 8px")
        self.btn_stop.clicked.connect(self._stop_scan)
        self.btn_stop.setEnabled(False)
        g3.addWidget(self.btn_start)
        g3.addWidget(self.btn_stop)
        lay.addWidget(grp3)

        lay.addStretch()
        return w

    # ── Tab: Manual ───────────────────────────────────────────────────
    def _tab_manual(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        grp = QGroupBox("Manual Motor Control")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Motor:"), 0, 0)
        self.cmb_man_motor = QComboBox()
        self.cmb_man_motor.addItems(["1", "2"])
        g.addWidget(self.cmb_man_motor, 0, 1)

        g.addWidget(QLabel("Degrees:"), 1, 0)
        self.spn_man_deg = QDoubleSpinBox()
        self.spn_man_deg.setRange(0.01, 360)
        self.spn_man_deg.setValue(5.0)
        g.addWidget(self.spn_man_deg, 1, 1)

        btn_fwd = QPushButton("▶  Move Forward (+)")
        btn_fwd.clicked.connect(lambda: self._manual_move(1))
        btn_rev = QPushButton("◀  Move Reverse (−)")
        btn_rev.clicked.connect(lambda: self._manual_move(-1))
        g.addWidget(btn_fwd, 2, 0)
        g.addWidget(btn_rev, 2, 1)

        btn_stop = QPushButton("⬛  STOP Motors")
        btn_stop.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold")
        btn_stop.clicked.connect(self._stop_motors)
        g.addWidget(btn_stop, 3, 0, 1, 2)

        btn_zero = QPushButton("Set Current Position as Zero")
        btn_zero.clicked.connect(self._zero_motors)
        g.addWidget(btn_zero, 4, 0, 1, 2)

        btn_home = QPushButton("Go to Home (Zero)")
        btn_home.clicked.connect(self._home_motors)
        g.addWidget(btn_home, 5, 0, 1, 2)

        g.addWidget(QLabel("Motor Speed (steps/s):"), 6, 0)
        self.spn_speed = QSpinBox()
        self.spn_speed.setRange(1, 10000)
        self.spn_speed.setValue(self.cfg["motors"]["max_speed_steps_per_sec"])
        btn_speed = QPushButton("Set Speed")
        btn_speed.clicked.connect(self._set_speed)
        g.addWidget(self.spn_speed, 6, 1)
        g.addWidget(btn_speed, 7, 0, 1, 2)

        self.lbl_pos = QLabel("Position: —")
        self.lbl_pos.setFont(QFont("Courier", 10))
        g.addWidget(self.lbl_pos, 8, 0, 1, 2)

        btn_update_pos = QPushButton("Refresh Position")
        btn_update_pos.clicked.connect(self._refresh_position)
        g.addWidget(btn_update_pos, 9, 0, 1, 2)
        lay.addWidget(grp)

        grp2 = QGroupBox("Manual Spectrometer")
        g2 = QVBoxLayout(grp2)
        btn_single = QPushButton("Acquire Single Spectrum")
        btn_single.clicked.connect(self._preview_spectrum)
        g2.addWidget(btn_single)
        lay.addWidget(grp2)

        lay.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────
    #  Hardware connection handlers
    # ─────────────────────────────────────────────────────────────────
    def _connect_motor(self):
        try:
            m_cfg = self.cfg["motors"]
            spd = int(m_cfg["steps_per_revolution"]) * int(m_cfg["microstep_divisor"])
            spd_deg = spd / 360.0
            self.motor = MotorController(
                port=self.inp_motor_port.text(),
                baud=int(self.inp_motor_baud.text()),
                timeout=float(m_cfg["timeout_s"]),
                steps_per_degree=spd_deg,
                max_speed=int(m_cfg["max_speed_steps_per_sec"]),
                m1_invert=bool(m_cfg["direction"]["motor1_invert"]),
                m2_invert=bool(m_cfg["direction"]["motor2_invert"]),
            )
            self.motor.connect()
            self.lbl_motor_status.setText("● Connected")
            self.lbl_motor_status.setStyleSheet("color: green")
            log.info("Motor controller connected")
        except Exception as e:
            QMessageBox.critical(self, "Motor Error", str(e))
            log.error("Motor connect failed: %s", e)

    def _connect_spec(self):
        try:
            s_cfg = self.cfg["spectrometer"]
            self.spec = Spectrometer(
                integration_time_ms=s_cfg["default_integration_time_ms"],
                scans_to_average=s_cfg["default_scans_to_average"],
                boxcar_width=s_cfg["default_boxcar_width"],
                wl_min=s_cfg["wavelength_min_nm"],
                wl_max=s_cfg["wavelength_max_nm"],
            )
            self.spec.connect()
            self.lbl_spec_status.setText("● Connected")
            self.lbl_spec_status.setStyleSheet("color: green")
            log.info("Spectrometer connected")
        except Exception as e:
            QMessageBox.critical(self, "Spectrometer Error", str(e))
            log.error("Spectrometer connect failed: %s", e)

    def _connect_source(self):
        try:
            k_cfg = self.cfg["sourcemeter"]
            self.source = SourceMeter(
                resource=self.inp_visa.text(),
                source_mode=k_cfg["source_mode"],
                voltage=k_cfg["default_voltage_v"],
                current_limit=k_cfg["default_current_limit_a"],
                settle_ms=k_cfg["settle_time_ms"],
                nplc=k_cfg["nplc"],
                # Verification parameters — fall back to safe defaults when
                # the config key is absent
                current_threshold=k_cfg.get("current_threshold_a", 1e-6),
                voltage_threshold=k_cfg.get("voltage_threshold_v", 1e-3),
                compliance_fraction=k_cfg.get("compliance_fraction", 0.95),
                verify_on_output_on=k_cfg.get("verify_on_output_on", True),
            )
            self.source.connect()
            self.lbl_src_status.setText("● Connected")
            self.lbl_src_status.setStyleSheet("color: green")
            log.info("Source meter connected")
        except Exception as e:
            QMessageBox.critical(self, "Source Meter Error", str(e))
            log.error("Source meter connect failed: %s", e)

    # ─────────────────────────────────────────────────────────────────
    #  Spectrometer controls
    # ─────────────────────────────────────────────────────────────────
    def _apply_spec_settings(self):
        if not self.spec:
            return
        try:
            actual_integration_time = self.spec.set_integration_time(self.spn_inttime.value())

            # Snap the spinner back to whatever was actually set
            # (in case it was clamped)
            self.spn_inttime.blockSignals(True)
            self.spn_inttime.setValue(actual_integration_time)
            self.spn_inttime.blockSignals(False)

            self.spec.set_scans_to_average(self.spn_avg.value())
            self.spec.set_boxcar_width(self.spn_boxcar.value())

        except ValueError as e:
            # Show the limit error and snap spinner to the clamped value
            QMessageBox.warning(self, "Integration Time Out of Range", str(e))

            # Update spinner to the clamped value the device is now using
            self.spn_inttime.blockSignals(True)
            self.spn_inttime.setValue(self.spec.integration_time_ms)
            self.spn_inttime.blockSignals(False)

        except Exception as e:
            QMessageBox.critical(self, "Spectrometer Error", str(e))

    def _collect_dark(self):
        if not self.spec:
            QMessageBox.warning(self, "Warning", "Spectrometer not connected")
            return
        try:
            self.spec.collect_dark()
            self.lbl_dark_status.setText("✓ Dark spectrum stored")
            self.lbl_dark_status.setStyleSheet("color: green")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _clear_dark(self):
        if self.spec:
            self.spec.clear_dark()
        self.lbl_dark_status.setText("No dark spectrum")
        self.lbl_dark_status.setStyleSheet("")

    def _preview_spectrum(self):
        if not self.spec:
            QMessageBox.warning(self, "Warning", "Spectrometer not connected")
            return
        try:
            wl, raw, corr = self.spec.acquire(
                subtract_dark=self.chk_dark.isChecked())
            self._plot_spectrum(None, wl, corr)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ─────────────────────────────────────────────────────────────────
    #  Source meter controls
    # ─────────────────────────────────────────────────────────────────
    def _apply_source_settings(self):
        if not self.source:
            QMessageBox.warning(self, "Warning", "Source meter not connected")
            return
        try:
            self.source.set_source_mode(self.cmb_source_mode.currentText())
            self.source.set_voltage(self.spn_voltage.value())
            self.source.set_current_limit(self.spn_current.value())
            self.source.settle_ms            = self.spn_settle.value()
            # Push verification settings from the UI onto the live object
            self.source.current_threshold    = self.spn_curr_thresh.value()
            self.source.voltage_threshold    = self.spn_volt_thresh.value()
            self.source.compliance_fraction  = self.spn_comp_frac.value()
            self.source.verify_on_output_on  = self.chk_verify.isChecked()
            self.lbl_verify_status.setText("")   # clear any stale status
            log.info("Source settings applied")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


    def _output_on(self):
        if not self.source:
            QMessageBox.warning(self, "Warning", "Source meter not connected")
            return
        try:
            self._apply_source_settings()
            # output_on() calls verify_operation() internally when
            # verify_on_output_on is True.  A SourceMeterError means the
            # output was enabled but the operating conditions are wrong;
            # we surface that distinctly from a generic instrument error.
            self.source.output_on()
            self.lbl_verify_status.setText("✔ Verification passed")
            self.lbl_verify_status.setStyleSheet("color: green")
            log.info("Output ON")
        except SourceMeterError as e:
            # Output is physically on but conditions are unsafe — turn it off
            # immediately and tell the user clearly what went wrong.
            self.source.output_off()
            self.lbl_verify_status.setText(f"✘ {e}")
            self.lbl_verify_status.setStyleSheet("color: red")
            QMessageBox.critical(
                self,
                "Verification Failed — Output Disabled",
                f"{e}\n\nThe output has been turned off automatically.",
            )
            log.error("Output ON verification failed: %s", e)
        except Exception as e:
            self.lbl_verify_status.setText("")
            QMessageBox.critical(self, "Error", str(e))
            log.error("Output ON failed: %s", e)


    def _output_off(self):
        if self.source:
            try:
                self.source.output_off()
                self.lbl_verify_status.setText("")   # clear status on deliberate off
                log.info("Output OFF")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


    def _manual_measure(self):
        if not self.source:
            QMessageBox.warning(self, "Warning", "Source meter not connected")
            return
        try:
            val  = self.source.measure()
            unit = "A" if self.source.source_mode == "VOLT" else "V"
            self.lbl_measure.setText(f"{val:.6e} {unit}")

            # Run a lightweight verification pass so the status label stays
            # current after every manual read, without raising a dialog.
            try:
                self.source.verify_operation()
                self.lbl_verify_status.setText("✔ Signal OK, no compliance")
                self.lbl_verify_status.setStyleSheet("color: green")
            except SourceMeterError as ve:
                self.lbl_verify_status.setText(f"✘ {ve}")
                self.lbl_verify_status.setStyleSheet("color: red")
                log.warning("Verification warning on manual measure: %s", ve)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ─────────────────────────────────────────────────────────────────
    #  Motor manual controls
    # ─────────────────────────────────────────────────────────────────
    def _manual_move(self, sign: int):
        if not self.motor:
            QMessageBox.warning(self, "Warning", "Motor not connected")
            return
        try:
            motor_id = int(self.cmb_man_motor.currentText())
            deg = sign * self.spn_man_deg.value()
            self.motor.move_degrees(motor_id, deg)
            self._refresh_position()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _stop_motors(self):
        if self.motor:
            self.motor.stop()

    def _zero_motors(self):
        if self.motor:
            self.motor.zero()
            self.lbl_pos.setText("Position: zeroed")

    def _home_motors(self):
        if self.motor:
            try:
                self.motor.home()
                self._refresh_position()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _set_speed(self):
        if self.motor:
            self.motor.set_speed(self.spn_speed.value())

    def _refresh_position(self):
        if self.motor:
            try:
                p1, p2 = self.motor.get_position()
                spd = self.motor.steps_per_degree
                self.lbl_pos.setText(
                    f"M1: {p1} steps ({p1/spd:.2f}°)  "
                    f"M2: {p2} steps ({p2/spd:.2f}°)")
            except Exception as e:
                log.error("Position query failed: %s", e)

    # ─────────────────────────────────────────────────────────────────
    #  Scan control
    # ─────────────────────────────────────────────────────────────────
    def _start_scan(self):
        if not self.motor:
            QMessageBox.critical(self, "Error", "Motor not connected")
            return
        if not self.spec:
            QMessageBox.critical(self, "Error", "Spectrometer not connected")
            return
        if not self.source:
            QMessageBox.critical(self, "Error", "Source meter not connected")
            return

        self._apply_spec_settings()
        self._apply_source_settings()

        params = {
            "angle_start"         : self.spn_ang_start.value(),
            "angle_end"           : self.spn_ang_end.value(),
            "angle_step"          : self.spn_ang_step.value(),
            "motor_id"            : int(self.cmb_motor_id.currentText()),
            "subtract_dark"       : self.chk_dark.isChecked(),
            "filename"            : self.inp_filename.text(),
            "save_dir"            : self.inp_savedir.text(),
            "timestamp_in_filename": self.chk_timestamp.isChecked(),
            "delimiter"           : self.cfg["data"]["delimiter"],
        }

        bridge = self.bridge
        callbacks = {
            "on_progress": lambda s, t, a: bridge.sig_progress.emit(s, t, a),
            "on_spectrum" : lambda a, w, c: bridge.sig_spectrum.emit(
                a, w, c),
            "on_status"  : lambda m: bridge.sig_status.emit(m),
            "on_finished": lambda p: bridge.sig_finished.emit(p),
            "on_error"   : lambda e: bridge.sig_error.emit(
                traceback.format_exc()),
        }

        self.worker = ScanWorker(self.motor, self.spec, self.source,
                                 params, callbacks)
        self.worker.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setValue(0)
        log.info("Scan started")

    def _stop_scan(self):
        if self.worker:
            self.worker.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ─────────────────────────────────────────────────────────────────
    #  Bridge slots
    # ─────────────────────────────────────────────────────────────────
    def _on_progress(self, step: int, total: int, angle: float):
        pct = int(100 * step / total)
        self.progress.setValue(pct)
        self.lbl_status.setText(
            f"Step {step}/{total} — {angle:.2f}°")

    def _on_spectrum(self, angle: float, wl, counts):
        self._plot_spectrum(angle, wl, counts)

    def _on_status(self, msg: str):
        self.lbl_status.setText(msg[:80])

    def _on_finished(self, paths):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setValue(100)

        if paths:
            path_spec, path_src = paths
            QMessageBox.information(
                self, "Scan Complete",
                f"Data saved:\n\n"
                f"Spectra:\n  {path_spec}\n\n"
                f"Sourcemeter:\n  {path_src}"
            )
        else:
            self.lbl_status.setText("Scan stopped")

    def _on_error(self, tb: str):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.critical(self, "Scan Error", tb)
        log.error("Scan error:\n%s", tb)

    # ─────────────────────────────────────────────────────────────────
    #  Plot
    # ─────────────────────────────────────────────────────────────────
    def _plot_spectrum(self, angle, wl, counts):
        self.ax.clear()
        self.ax.plot(wl, counts, lw=0.8, color="#2980b9")
        title = f"Spectrum at {angle:.2f}°" if angle is not None else "Preview Spectrum"
        self.ax.set_title(title)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (counts)")
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    # ─────────────────────────────────────────────────────────────────
    #  Misc
    # ─────────────────────────────────────────────────────────────────
    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Save Directory",
                                             self.inp_savedir.text())
        if d:
            self.inp_savedir.setText(d)

    def closeEvent(self, event):
        # Clean shutdown
        if self.worker and self.worker.is_running():
            self.worker.stop()
        if self.motor:
            self.motor.disconnect()
        if self.spec:
            self.spec.disconnect()
        if self.source:
            self.source.disconnect()
        event.accept()


# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════
def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    cfg = load_config("config.yaml")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(cfg)
    win.show()
    sys.exit(app.exec_())