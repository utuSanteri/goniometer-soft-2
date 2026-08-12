import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QMessageBox,
)
from PyQt5.QtGui import QFont

from gui.hw_imports import SourceMeterError

log = logging.getLogger(__name__)


class SourceTab(QWidget):
    """Source-meter configuration, output control, measurement."""

    def __init__(self, hw, cfg, parent=None):
        super().__init__(parent)
        self.hw  = hw
        self.cfg = cfg
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        # ── Source Settings ───────────────────────────────────────────
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
        self.spn_voltage.setValue(
            self.cfg["sourcemeter"]["default_voltage_v"])
        g.addWidget(self.spn_voltage, 1, 1)

        g.addWidget(QLabel("Current limit (A):"), 2, 0)
        self.spn_current = QDoubleSpinBox()
        self.spn_current.setRange(0, 1.05)
        self.spn_current.setDecimals(8)
        self.spn_current.setValue(
            self.cfg["sourcemeter"]["default_current_limit_a"])
        g.addWidget(self.spn_current, 2, 1)

        g.addWidget(QLabel("Settle time (ms):"), 3, 0)
        self.spn_settle = QDoubleSpinBox()
        self.spn_settle.setRange(0, 5000)
        self.spn_settle.setValue(
            self.cfg["sourcemeter"]["settle_time_ms"])
        g.addWidget(self.spn_settle, 3, 1)

        self.btn_apply_src = QPushButton("Apply Settings")
        self.btn_apply_src.clicked.connect(self.apply_settings)
        g.addWidget(self.btn_apply_src, 4, 0, 1, 2)
        lay.addWidget(grp)

        # ── Verification Settings ────────────────────────────────────
        grp_ver = QGroupBox("Verification Settings")
        gv = QGridLayout(grp_ver)

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

        # ── Manual Output Control ────────────────────────────────────
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

        # ── Measurement ──────────────────────────────────────────────
        grp3 = QGroupBox("Measurement")
        g3 = QVBoxLayout(grp3)
        self.btn_measure = QPushButton("Read Measurement")
        self.btn_measure.clicked.connect(self._manual_measure)
        g3.addWidget(self.btn_measure)
        self.lbl_measure = QLabel("—")
        self.lbl_measure.setFont(QFont("Courier", 14))
        g3.addWidget(self.lbl_measure)

        self.lbl_verify_status = QLabel("")
        self.lbl_verify_status.setFont(QFont("Courier", 10))
        self.lbl_verify_status.setWordWrap(True)
        g3.addWidget(self.lbl_verify_status)

        lay.addWidget(grp3)
        lay.addStretch()

    # ── Public ────────────────────────────────────────────────────────
    def apply_settings(self):
        if not self.hw.source:
            QMessageBox.warning(
                self, "Warning", "Source meter not connected")
            return
        try:
            self.hw.source.set_source_mode(
                self.cmb_source_mode.currentText())
            self.hw.source.set_voltage(self.spn_voltage.value())
            self.hw.source.set_current_limit(self.spn_current.value())
            self.hw.source.settle_ms           = self.spn_settle.value()
            self.hw.source.current_threshold   = self.spn_curr_thresh.value()
            self.hw.source.voltage_threshold   = self.spn_volt_thresh.value()
            self.hw.source.compliance_fraction = self.spn_comp_frac.value()
            self.hw.source.verify_on_output_on = self.chk_verify.isChecked()
            self.lbl_verify_status.setText("")
            log.info("Source settings applied")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Private ───────────────────────────────────────────────────────
    def _output_on(self):
        if not self.hw.source:
            QMessageBox.warning(
                self, "Warning", "Source meter not connected")
            return
        try:
            self.apply_settings()
            self.hw.source.output_on()
            self.lbl_verify_status.setText("✔ Verification passed")
            self.lbl_verify_status.setStyleSheet("color: green")
            log.info("Output ON")
        except SourceMeterError as e:
            self.hw.source.output_off()
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
        if self.hw.source:
            try:
                self.hw.source.output_off()
                self.lbl_verify_status.setText("")
                log.info("Output OFF")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _manual_measure(self):
        if not self.hw.source:
            QMessageBox.warning(
                self, "Warning", "Source meter not connected")
            return
        try:
            val  = self.hw.source.measure()
            unit = ("A" if self.hw.source.source_mode == "VOLT"
                    else "V")
            self.lbl_measure.setText(f"{val:.6e} {unit}")

            try:
                self.hw.source.verify_operation()
                self.lbl_verify_status.setText(
                    "✔ Signal OK, no compliance")
                self.lbl_verify_status.setStyleSheet("color: green")
            except SourceMeterError as ve:
                self.lbl_verify_status.setText(f"✘ {ve}")
                self.lbl_verify_status.setStyleSheet("color: red")
                log.warning(
                    "Verification warning on manual measure: %s", ve)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))