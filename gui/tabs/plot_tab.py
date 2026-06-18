"""
Plot tab — file-management controls (left panel) and multi-plot
analysis canvas (right panel) for viewing saved scan data.
"""

import os
import re
import logging

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QCheckBox,
    QComboBox, QMessageBox, QSizePolicy, QSpacerItem,
)
from PyQt5.QtCore import pyqtSignal

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.colors import Normalize
from matplotlib.gridspec import GridSpec

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Data loader
# ═══════════════════════════════════════════════════════════════════

def load_scan_file(path: str, sourcemeter_path: str = None) -> dict:
    """
    Load spectrum + sourcemeter files produced by ``_save()``.

    Returns dict with keys:
        meta, wl, ang, v, i, comp, raw, corr, path
    """
    # ── Auto-detect sourcemeter path ──────────────────────────────
    if sourcemeter_path is None:
        base, ext = os.path.splitext(path)
        m = re.match(r'^(.+?)_(\d{8}_\d{6})$', base)
        if m:
            candidate = f"{m.group(1)}_sourcemeter_{m.group(2)}{ext}"
        else:
            candidate = f"{base}_sourcemeter{ext}"
        if os.path.isfile(candidate):
            sourcemeter_path = candidate

    # ── Spectrum file ─────────────────────────────────────────────
    with open(path) as f:
        lines = f.read().splitlines()

    meta, data_lines = {}, []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            content = s[1:].strip()
            if ':' in content:
                k, v = content.split(':', 1)
                meta[k.strip()] = v.strip()
            continue
        data_lines.append(s)

    if not data_lines:
        raise ValueError(f"No data lines in {path}")

    # Detect delimiter
    first = data_lines[0]
    delimiter = '\t'
    for d in [';', '\t', ',']:
        if d in first:
            delimiter = d
            break

    wl_parts = first.split(delimiter)
    wl = np.array([float(x) for x in wl_parts[1:]])
    n = len(wl)

    body = data_lines[1:]
    n_angles = len(body) // 2
    if n_angles == 0 or len(body) != 2 * n_angles:
        raise ValueError(
            f"Expected even number of data rows, got {len(body)}")

    def _parse_block(block):
        angles, values = [], []
        for row in block:
            parts = row.split(delimiter)
            angles.append(float(parts[0]))
            values.append([float(x) for x in parts[1:1 + n]])
        return np.array(angles), np.array(values)

    ang, raw = _parse_block(body[:n_angles])
    _, corr  = _parse_block(body[n_angles:])

    # ── Sourcemeter file ──────────────────────────────────────────
    volt = np.zeros(n_angles)
    curr = np.zeros(n_angles)
    comp = np.zeros(n_angles, dtype=bool)

    if sourcemeter_path and os.path.isfile(sourcemeter_path):
        with open(sourcemeter_path) as f:
            src_lines = f.read().splitlines()

        src_delim = delimiter
        for sl in src_lines:
            ss = sl.strip()
            if ss and not ss.startswith('#'):
                for d in [';', '\t', ',']:
                    if d in ss:
                        src_delim = d
                        break
                break

        idx = 0
        for line in src_lines:
            ss = line.strip()
            if not ss or ss.startswith('#'):
                continue
            try:
                float(ss.split(src_delim)[0])
            except ValueError:
                continue
            parts = ss.split(src_delim)
            if idx < n_angles:
                volt[idx] = float(parts[1])
                curr[idx] = float(parts[2])
                comp[idx] = bool(int(float(parts[3])))
                idx += 1

    return dict(meta=meta, wl=wl, ang=ang, v=volt, i=curr,
                comp=comp, raw=raw, corr=corr, path=path)


# ═══════════════════════════════════════════════════════════════════
#  Analysis canvas  (placed on the RIGHT panel by MainWindow)
# ═══════════════════════════════════════════════════════════════════

class ScanAnalysisCanvas(QWidget):
    """
    Standalone widget: toolbar + matplotlib figure with
    waterfall / heatmap / integrated+electrical subplots.

    MainWindow places this in the right panel alongside PlotPanel
    (inside a QStackedWidget).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = None
        self._show_raw = False
        self._colorbars = []
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar = NavigationToolbar(self.canvas, self)

        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, stretch=1)

    # ── Public API ────────────────────────────────────────────────
    def plot(self, data: dict, show_raw: bool = False):
        self._data = data
        self._show_raw = show_raw
        self._redraw()

    def set_show_raw(self, raw: bool):
        self._show_raw = raw
        if self._data is not None:
            self._redraw()

    def clear(self):
        self._data = None
        self._remove_colorbars()
        self.fig.clear()
        self.canvas.draw_idle()

    # ── Internals ─────────────────────────────────────────────────
    def _remove_colorbars(self):
        for cb in self._colorbars:
            try:
                cb.remove()
            except Exception:
                pass
        self._colorbars.clear()

    def _redraw(self):
        d = self._data
        if d is None:
            return

        sp  = d['raw'] if self._show_raw else d['corr']
        wl  = d['wl']
        ang = d['ang']
        n   = len(ang)
        tag = 'Raw counts' if self._show_raw else 'Corrected counts'

        self._remove_colorbars()
        self.fig.clear()

        gs = GridSpec(3, 1, figure=self.fig, height_ratios=[1, 1, 1])
        ax_wf  = self.fig.add_subplot(gs[0])
        ax_hm  = self.fig.add_subplot(gs[1])
        ax_int = self.fig.add_subplot(gs[2])

        cmap_name = 'plasma'
        colors = matplotlib.cm.get_cmap(cmap_name)(
            np.linspace(0, 1, n))

        # ── 1. Waterfall ──────────────────────────────────────────
        for i in range(n):
            ax_wf.plot(wl, sp[i], color=colors[i], lw=0.8, alpha=0.8)
        ax_wf.set_xlabel('Wavelength (nm)')
        ax_wf.set_ylabel(tag)
        ax_wf.set_title('Spectra per angle', fontsize=10)
        ax_wf.grid(True, alpha=0.25)

        sm = matplotlib.cm.ScalarMappable(
            cmap=cmap_name, norm=Normalize(ang.min(), ang.max()))
        sm.set_array([])
        cb1 = self.fig.colorbar(sm, ax=ax_wf, label='Angle (°)',
                                pad=0.02)
        self._colorbars.append(cb1)

        # ── 2. Heatmap ───────────────────────────────────────────
        extent = [wl[0], wl[-1], ang[-1], ang[0]]
        im = ax_hm.imshow(sp, aspect='auto', cmap='inferno',
                          origin='upper', extent=extent)
        ax_hm.set_xlabel('Wavelength (nm)')
        ax_hm.set_ylabel('Angle (°)')
        ax_hm.set_title('Angle–wavelength heatmap', fontsize=10)
        cb2 = self.fig.colorbar(im, ax=ax_hm, label=tag, pad=0.02)
        self._colorbars.append(cb2)

        # ── 3. Integrated + Electrical ────────────────────────────
        integrated = sp.sum(axis=1)

        ln1 = ax_int.plot(ang, integrated, 'o-', color='#2980b9',
                          lw=1.5, ms=4, label='Integrated counts')

        if d['comp'].any():
            ax_int.scatter(ang[d['comp']], integrated[d['comp']],
                           color='red', marker='x', s=60, zorder=5,
                           label='Compliance')
            for a in ang[d['comp']]:
                ax_int.axvline(a, color='red', ls='--', alpha=0.3)

        ax_int.set_xlabel('Angle (°)')
        ax_int.set_ylabel('Integrated counts', color='#2980b9')
        ax_int.tick_params(axis='y', labelcolor='#2980b9')
        ax_int.grid(True, alpha=0.25)
        ax_int.set_title('Integrated spectrum & electrical',
                         fontsize=10)

        has_elec = np.any(d['v'] != 0) or np.any(d['i'] != 0)
        if has_elec:
            ax_el = ax_int.twinx()
            ln2 = ax_el.plot(ang, d['v'], 's-', color='#27ae60',
                             lw=1.2, ms=3, label='Voltage (V)')
            ln3 = ax_el.plot(ang, d['i'] * 1e3, '^-', color='#e67e22',
                             lw=1.2, ms=3, label='Current (mA)')
            ax_el.set_ylabel('V  /  mA')
            lns = ln1 + ln2 + ln3
            ax_int.legend(lns, [l.get_label() for l in lns],
                          loc='upper left', fontsize=8)
        else:
            ax_int.legend(loc='upper left', fontsize=8)

        self.fig.suptitle(os.path.basename(d['path']),
                          fontsize=11, fontweight='bold')
        self.canvas.draw_idle()


# ═══════════════════════════════════════════════════════════════════
#  PlotTab  (placed on the LEFT panel as a tab — controls only)
# ═══════════════════════════════════════════════════════════════════

class PlotTab(QWidget):
    """
    Narrow control panel for loading / browsing saved scan files.

    The heavy plotting is done by ``self.analysis_canvas``
    (a :class:`ScanAnalysisCanvas`), which **MainWindow** must place
    into the right-side panel.

    Signals
    -------
    sig_show_analysis
        Emitted when the user loads a file — MainWindow should switch
        the right panel to show ``self.analysis_canvas``.
    sig_show_live
        Emitted when the user clears all files — MainWindow can
        switch back to the live PlotPanel.
    """

    sig_show_analysis = pyqtSignal()
    sig_show_live     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datasets = {}                          # path → data dict

        # The canvas that MainWindow places on the right
        self.analysis_canvas = ScanAnalysisCanvas()

        self._build_ui()

    # ── UI (narrow — fits in 400-480 px) ──────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        # ── File management ───────────────────────────────────────
        file_grp = QGroupBox("Scan Files")
        file_lay = QVBoxLayout(file_grp)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add file(s)…")
        self.btn_add.clicked.connect(self._add_files)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self._remove_current)
        self.btn_clear = QPushButton("Clear all")
        self.btn_clear.clicked.connect(self._clear_files)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_clear)
        file_lay.addLayout(btn_row)

        self.cmb_files = QComboBox()
        self.cmb_files.setToolTip("Select a loaded scan file to view")
        self.cmb_files.currentIndexChanged.connect(
            self._on_file_selected)
        file_lay.addWidget(self.cmb_files)

        lay.addWidget(file_grp)

        # ── Display options ───────────────────────────────────────
        opt_grp = QGroupBox("Display Options")
        opt_lay = QVBoxLayout(opt_grp)

        self.chk_raw = QCheckBox("Show raw counts (instead of corrected)")
        self.chk_raw.toggled.connect(self._on_raw_toggled)
        opt_lay.addWidget(self.chk_raw)

        lay.addWidget(opt_grp)

        # ── Summary ──────────────────────────────────────────────
        info_grp = QGroupBox("File Summary")
        info_lay = QVBoxLayout(info_grp)

        self.lbl_info = QLabel("No file loaded")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(
            "QLabel { padding: 4px; }")
        info_lay.addWidget(self.lbl_info)

        # Sourcemeter status
        self.lbl_sm = QLabel("")
        self.lbl_sm.setWordWrap(True)
        self.lbl_sm.setStyleSheet(
            "QLabel { color: grey; padding: 2px; }")
        info_lay.addWidget(self.lbl_sm)

        lay.addWidget(info_grp)

        # ── Metadata ─────────────────────────────────────────────
        meta_grp = QGroupBox("File Metadata")
        meta_lay = QVBoxLayout(meta_grp)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet(
            "QLabel { font-family: monospace; font-size: 9pt; "
            "padding: 4px; }")
        meta_lay.addWidget(self.lbl_meta)

        lay.addWidget(meta_grp)

        lay.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum,
                        QSizePolicy.Expanding))

    # ── File handling ─────────────────────────────────────────────
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Spectrum Scan Files", "",
            "Scan Files (*.txt *.dat);;All Files (*)")
        if not paths:
            return

        # Skip sourcemeter companion files
        paths = [p for p in paths
                 if '_sourcemeter_' not in os.path.basename(p)]

        errors = []
        for p in paths:
            if p in self._datasets:
                continue
            try:
                data = load_scan_file(p)
                self._datasets[p] = data
                self.cmb_files.addItem(os.path.basename(p), userData=p)
                log.info("Loaded %s", os.path.basename(p))
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")
                log.warning("Failed to load %s: %s",
                            os.path.basename(p), e)

        if errors:
            QMessageBox.warning(
                self, "Load Warnings",
                "Some files could not be loaded:\n\n"
                + "\n".join(errors))

        if self.cmb_files.count():
            self.cmb_files.setCurrentIndex(
                self.cmb_files.count() - 1)
            self.sig_show_analysis.emit()

    def _remove_current(self):
        idx = self.cmb_files.currentIndex()
        if idx < 0:
            return
        path = self.cmb_files.currentData()
        self._datasets.pop(path, None)
        self.cmb_files.removeItem(idx)
        if self.cmb_files.count() == 0:
            self._clear_display()
            self.sig_show_live.emit()

    def _clear_files(self):
        self._datasets.clear()
        self.cmb_files.clear()
        self._clear_display()
        self.sig_show_live.emit()

    def _clear_display(self):
        self.analysis_canvas.clear()
        self.lbl_info.setText("No file loaded")
        self.lbl_sm.clear()
        self.lbl_meta.clear()

    def _on_file_selected(self, idx):
        if idx < 0:
            return
        path = self.cmb_files.currentData()
        if path is None or path not in self._datasets:
            return
        data = self._datasets[path]
        self.analysis_canvas.plot(data, self.chk_raw.isChecked())
        self._show_summary(data)
        self.sig_show_analysis.emit()

    def _on_raw_toggled(self, checked):
        self.analysis_canvas.set_show_raw(checked)

    # ── Programmatic API (called by MainWindow after scan) ────────
    def load_and_show(self, path: str):
        """Load a file and select it (e.g. after a scan finishes)."""
        if path not in self._datasets:
            try:
                data = load_scan_file(path)
            except Exception as e:
                log.error("Cannot load %s: %s", path, e)
                return
            self._datasets[path] = data
            self.cmb_files.addItem(os.path.basename(path),
                                   userData=path)

        idx = self.cmb_files.findData(path)
        if idx >= 0:
            self.cmb_files.setCurrentIndex(idx)
        self.sig_show_analysis.emit()

    # ── Summary display ───────────────────────────────────────────
    def _show_summary(self, data: dict):
        d = data
        ang, wl, corr = d['ang'], d['wl'], d['corr']

        flat_idx = np.argmax(corr)
        r, c = np.unravel_index(flat_idx, corr.shape)

        integrated = corr.sum(axis=1)
        best_idx = np.argmax(integrated)

        self.lbl_info.setText(
            f"<b>Angles:</b> {len(ang)}  "
            f"({ang[0]:.1f}° → {ang[-1]:.1f}°)<br>"
            f"<b>Wavelengths:</b> {len(wl)}  "
            f"({wl[0]:.1f} – {wl[-1]:.1f} nm)<br>"
            f"<b>Peak:</b> {corr[r, c]:.1f}  @  "
            f"{wl[c]:.2f} nm, {ang[r]:.1f}°<br>"
            f"<b>Best integrated angle:</b> {ang[best_idx]:.1f}°<br>"
            f"<b>Compliance:</b> {d['comp'].sum()} / {len(d['comp'])}"
        )

        has_sm = np.any(d['v'] != 0) or np.any(d['i'] != 0)
        if has_sm:
            self.lbl_sm.setText(
                f"V: {d['v'].min():.3f} – {d['v'].max():.3f} V\n"
                f"I: {d['i'].min()*1e3:.3f} – "
                f"{d['i'].max()*1e3:.3f} mA")
        else:
            self.lbl_sm.setText("No sourcemeter data found")

        # Metadata from file header
        if d['meta']:
            lines = [f"{k}: {v}" for k, v in d['meta'].items()]
            self.lbl_meta.setText("\n".join(lines))
        else:
            self.lbl_meta.setText("(none)")