import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal

from gui.hw_imports import MotorController, Spectrometer, SourceMeter

log = logging.getLogger(__name__)


class ConnectTab(QWidget):
    """Hardware connection management."""

    sig_motor_connected  = pyqtSignal()
    sig_spec_connected   = pyqtSignal()
    sig_source_connected = pyqtSignal()

    def __init__(self, hw, cfg, parent=None):
        super().__init__(parent)
        self.hw  = hw
        self.cfg = cfg
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

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
        self.inp_visa = QLineEdit(
            self.cfg["sourcemeter"]["visa_resource"])
        g3.addWidget(self.inp_visa, 0, 1)
        self.btn_src_connect = QPushButton("Connect Source Meter")
        self.btn_src_connect.clicked.connect(self._connect_source)
        g3.addWidget(self.btn_src_connect, 1, 0, 1, 2)
        self.lbl_src_status = QLabel("● Disconnected")
        self.lbl_src_status.setStyleSheet("color: red")
        g3.addWidget(self.lbl_src_status, 2, 0, 1, 2)
        lay.addWidget(grp3)

        lay.addStretch()

    # ── Handlers ──────────────────────────────────────────────────────
    def _connect_motor(self):
        try:
            m = self.cfg["motors"]
            spd = int(m["steps_per_revolution"]) * int(m["microstep_divisor"])
            self.hw.motor = MotorController(
                port=self.inp_motor_port.text(),
                baud=int(self.inp_motor_baud.text()),
                timeout=float(m["timeout_s"]),
                steps_per_degree=spd / 360.0,
                max_speed=int(m["max_speed_steps_per_sec"]),
                m1_invert=bool(m["direction"]["motor1_invert"]),
                m2_invert=bool(m["direction"]["motor2_invert"]),
            )
            self.hw.motor.connect()
            self.lbl_motor_status.setText("● Connected")
            self.lbl_motor_status.setStyleSheet("color: green")
            self.sig_motor_connected.emit()
            log.info("Motor controller connected")
        except Exception as e:
            QMessageBox.critical(self, "Motor Error", str(e))
            log.error("Motor connect failed: %s", e)

    def _connect_spec(self):
        try:
            s = self.cfg["spectrometer"]
            self.hw.spec = Spectrometer(
                integration_time_ms=s["default_integration_time_ms"],
                scans_to_average=s["default_scans_to_average"],
                boxcar_width=s["default_boxcar_width"],
                wl_min=s["wavelength_min_nm"],
                wl_max=s["wavelength_max_nm"],
            )
            self.hw.spec.connect()
            self.lbl_spec_status.setText("● Connected")
            self.lbl_spec_status.setStyleSheet("color: green")
            self.sig_spec_connected.emit()
            log.info("Spectrometer connected")
        except Exception as e:
            QMessageBox.critical(self, "Spectrometer Error", str(e))
            log.error("Spectrometer connect failed: %s", e)

    def _connect_source(self):
        try:
            k = self.cfg["sourcemeter"]
            self.hw.source = SourceMeter(
                resource=self.inp_visa.text(),
                source_mode=k["source_mode"],
                voltage=k["default_voltage_v"],
                current_limit=k["default_current_limit_a"],
                settle_ms=k["settle_time_ms"],
                nplc=k["nplc"],
                current_threshold=k.get("current_threshold_a", 1e-6),
                voltage_threshold=k.get("voltage_threshold_v", 1e-3),
                compliance_fraction=k.get("compliance_fraction", 0.95),
                verify_on_output_on=k.get("verify_on_output_on", True),
            )
            self.hw.source.connect()
            self.lbl_src_status.setText("● Connected")
            self.lbl_src_status.setStyleSheet("color: green")
            self.sig_source_connected.emit()
            log.info("Source meter connected")
        except Exception as e:
            QMessageBox.critical(self, "Source Meter Error", str(e))
            log.error("Source meter connect failed: %s", e)