"""
Spin box + unit selector (A / mA / µA) for entering a current.

The value is always exchanged in amps via ``amps()`` / ``set_amps()``;
the unit only changes how it is displayed and typed.
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QDoubleSpinBox, QComboBox

# unit label → (scale to amps, decimals, single step)
# Decimals are chosen so every unit resolves 1 nA.
_UNITS = {
    "A":  (1.0,  9, 0.001),
    "mA": (1e-3, 6, 1.0),
    "µA": (1e-6, 3, 1.0),
}


class CurrentInput(QWidget):

    def __init__(self, max_amps: float, amps: float = 0.0,
                 unit: str = "mA", parent=None):
        super().__init__(parent)
        self._max_amps = max_amps

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.spin = QDoubleSpinBox()
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(list(_UNITS))
        lay.addWidget(self.spin, stretch=1)
        lay.addWidget(self.cmb_unit)

        self._unit = unit if unit in _UNITS else "A"
        self.cmb_unit.setCurrentText(self._unit)
        self._apply_unit(amps)
        self.cmb_unit.currentTextChanged.connect(self._on_unit_changed)

    # ── Public API ────────────────────────────────────────────────────
    def amps(self) -> float:
        return self.spin.value() * _UNITS[self._unit][0]

    def set_amps(self, a: float):
        self.spin.setValue(a / _UNITS[self._unit][0])

    def setToolTip(self, text: str):
        self.spin.setToolTip(text)
        self.cmb_unit.setToolTip(text)

    # ── Private ───────────────────────────────────────────────────────
    def _apply_unit(self, amps: float):
        scale, decimals, step = _UNITS[self._unit]
        self.spin.setDecimals(decimals)
        self.spin.setRange(0.0, self._max_amps / scale)
        self.spin.setSingleStep(step)
        self.spin.setValue(amps / scale)

    def _on_unit_changed(self, unit: str):
        amps = self.amps()          # keep the physical value unchanged
        self._unit = unit
        self._apply_unit(amps)
