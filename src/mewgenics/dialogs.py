"""Dialog windows: TagManager, ThresholdPreferences, OptimizerSearchSettings, SaveSelector."""
from __future__ import annotations

import os
import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QListWidget, QListWidgetItem, QFileDialog,
)
from PySide6.QtCore import Qt, QSize

from mewgenics.utils.localization import _tr
from mewgenics.utils.tags import (
    TAG_PRESET_COLORS, _TAG_DEFS, _save_tag_definitions, _next_tag_id,
)
from mewgenics.utils.thresholds import (
    _normalize_threshold_preferences,
    _load_threshold_preferences,
    _effective_thresholds_for_cats,
)
from mewgenics.utils.optimizer_settings import (
    _normalize_optimizer_search_settings,
    _load_optimizer_search_settings,
    _OPTIMIZER_SEARCH_DEFAULTS,
)

from save_parser import Cat


# ---------------------------------------------------------------------------
# TagManagerDialog
# ---------------------------------------------------------------------------

class TagManagerDialog(QDialog):
    """Dialog for creating, editing, and deleting tag definitions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Tags")
        self.setMinimumWidth(380)
        self.setStyleSheet(
            "QDialog { background:#1a1a32; color:#ddd; }"
            "QLabel { color:#ddd; }"
            "QLineEdit { background:#101024; color:#ddd; border:1px solid #2a2a4a;"
            " padding:4px 8px; border-radius:4px; }"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Tag list area
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_widget)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(300)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")
        layout.addWidget(scroll)

        # Add new tag section
        add_box = QWidget()
        add_layout = QHBoxLayout(add_box)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(6)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("New tag name...")
        self._name_input.setMaxLength(20)
        add_layout.addWidget(self._name_input, 1)

        # Color preset buttons
        self._selected_color = TAG_PRESET_COLORS[0]
        self._color_btns = []
        for color in TAG_PRESET_COLORS:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                f"QPushButton {{ background:{color}; border:2px solid transparent;"
                f" border-radius:11px; }}"
                f"QPushButton:hover {{ border-color:#fff; }}"
            )
            btn.clicked.connect(lambda checked, c=color: self._select_color(c))
            self._color_btns.append((btn, color))
            add_layout.addWidget(btn)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setStyleSheet(
            "QPushButton { background:#2a4a2a; color:#6c6; font-size:16px; font-weight:bold;"
            " border:none; border-radius:14px; }"
            "QPushButton:hover { background:#3a6a3a; }"
        )
        add_btn.clicked.connect(self._add_tag)
        add_layout.addWidget(add_btn)

        layout.addWidget(add_box)
        self._update_color_selection()
        self._rebuild_list()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background:#252545; color:#aaa; padding:6px 16px;"
            " border:none; border-radius:4px; }"
            "QPushButton:hover { background:#353565; color:#ddd; }"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def _select_color(self, color: str):
        self._selected_color = color
        self._update_color_selection()

    def _update_color_selection(self):
        for btn, color in self._color_btns:
            if color == self._selected_color:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{color}; border:2px solid #fff;"
                    f" border-radius:11px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{color}; border:2px solid transparent;"
                    f" border-radius:11px; }}"
                    f"QPushButton:hover {{ border-color:#fff; }}"
                )

    def _add_tag(self):
        name = self._name_input.text().strip()
        tag_id = _next_tag_id()
        _TAG_DEFS.append({"id": tag_id, "name": name, "color": self._selected_color})
        _save_tag_definitions()
        self._name_input.clear()
        self._rebuild_list()

    def _delete_tag(self, tag_id: str):
        _TAG_DEFS[:] = [td for td in _TAG_DEFS if td["id"] != tag_id]
        _save_tag_definitions()
        mw = self.parent()
        if hasattr(mw, '_cats'):
            for cat in mw._cats:
                current = list(getattr(cat, 'tags', None) or [])
                if tag_id in current:
                    current.remove(tag_id)
                    cat.tags = current
        self._rebuild_list()

    def _rename_tag(self, tag_id: str, new_name: str):
        for td in _TAG_DEFS:
            if td["id"] == tag_id:
                td["name"] = new_name.strip()
                break
        _save_tag_definitions()

    def _recolor_tag(self, tag_id: str, new_color: str):
        for td in _TAG_DEFS:
            if td["id"] == tag_id:
                td["color"] = new_color
                break
        _save_tag_definitions()
        self._rebuild_list()

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not _TAG_DEFS:
            empty = QLabel("No tags defined yet")
            empty.setStyleSheet("color:#666; font-style:italic; padding:10px;")
            empty.setAlignment(Qt.AlignCenter)
            self._list_layout.addWidget(empty)
        else:
            for td in _TAG_DEFS:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 2, 4, 2)
                rl.setSpacing(8)

                swatch = QPushButton()
                swatch.setFixedSize(20, 20)
                swatch.setStyleSheet(
                    f"QPushButton {{ background:{td['color']}; border:none; border-radius:10px; }}"
                    f"QPushButton:hover {{ border:2px solid #fff; }}"
                )
                tag_id = td["id"]
                swatch.clicked.connect(lambda checked, tid=tag_id: self._show_color_picker(tid))
                rl.addWidget(swatch)

                name_edit = QLineEdit(td["name"])
                name_edit.setMaxLength(20)
                name_edit.setStyleSheet(
                    "QLineEdit { background:transparent; color:#ddd; border:none;"
                    " border-bottom:1px solid #2a2a4a; padding:2px 4px; font-size:12px; }"
                    "QLineEdit:focus { border-bottom-color:#5a5a8a; }"
                )
                name_edit.editingFinished.connect(
                    lambda tid=tag_id, le=name_edit: self._rename_tag(tid, le.text())
                )
                rl.addWidget(name_edit, 1)

                del_btn = QPushButton("x")
                del_btn.setFixedSize(22, 22)
                del_btn.setStyleSheet(
                    "QPushButton { background:transparent; color:#855; font-size:12px;"
                    " font-weight:bold; border:1px solid #433; border-radius:11px; }"
                    "QPushButton:hover { background:#4a2020; color:#f88; border-color:#855; }"
                )
                del_btn.clicked.connect(lambda checked, tid=tag_id: self._delete_tag(tid))
                rl.addWidget(del_btn)

                self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _show_color_picker(self, tag_id: str):
        popup = QDialog(self)
        popup.setWindowTitle("Pick Color")
        popup.setFixedWidth(200)
        popup.setStyleSheet("QDialog { background:#1a1a32; }")
        grid = QGridLayout(popup)
        grid.setSpacing(6)
        for i, color in enumerate(TAG_PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(
                f"QPushButton {{ background:{color}; border:2px solid transparent;"
                f" border-radius:15px; }}"
                f"QPushButton:hover {{ border-color:#fff; }}"
            )
            btn.clicked.connect(lambda checked, c=color: (self._recolor_tag(tag_id, c), popup.accept()))
            grid.addWidget(btn, i // 4, i % 4)
        popup.exec()


# ---------------------------------------------------------------------------
# ThresholdPreferencesDialog
# ---------------------------------------------------------------------------

class ThresholdPreferencesDialog(QDialog):
    def __init__(self, parent=None, prefs: dict | None = None, cats: list[Cat] | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(_tr("thresholds.title", default="Donation / Exceptional Thresholds"))
        self.setMinimumWidth(520)
        self.setStyleSheet(
            "QDialog { background:#0a0a18; }"
            "QLabel { color:#cfcfe0; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:6px 12px; font-size:11px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
            "QCheckBox { color:#d8d8e8; }"
            "QSpinBox, QDoubleSpinBox { background:#0d0d1c; color:#ddd; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:3px 6px; }"
        )

        self._cats = list(cats or [])
        self._prefs = _normalize_threshold_preferences(prefs or _load_threshold_preferences())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        desc = QLabel(_tr(
            "thresholds.description",
            default="Edit the donation and exceptional thresholds used by the sidebar filters."
        ))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px; color:#a8a8c0;")
        root.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self._exceptional_spin = QSpinBox()
        self._exceptional_spin.setRange(0, 999)
        self._exceptional_spin.setValue(self._prefs["exceptional_sum_threshold"])
        self._exceptional_spin.valueChanged.connect(self._update_preview)

        self._donation_spin = QSpinBox()
        self._donation_spin.setRange(0, 999)
        self._donation_spin.setValue(self._prefs["donation_sum_threshold"])
        self._donation_spin.valueChanged.connect(self._update_preview)

        self._top_stat_spin = QSpinBox()
        self._top_stat_spin.setRange(0, 20)
        self._top_stat_spin.setValue(self._prefs["donation_max_top_stat"])
        self._top_stat_spin.valueChanged.connect(self._update_preview)

        self._planner_trait_check = QCheckBox(_tr(
            "thresholds.planner_trait_toggle",
            default="Count cats missing selected mutation/ability traits as donation candidates",
        ))
        self._planner_trait_check.setChecked(bool(self._prefs["donation_missing_planner_traits"]))
        self._planner_trait_check.setToolTip(_tr(
            "thresholds.planner_trait_toggle.tooltip",
            default="When enabled, cats that do not carry any selected mutation or ability traits will count as donation candidates.",
        ))
        self._planner_trait_check.toggled.connect(self._update_preview)

        self._adaptive_check = QCheckBox(_tr(
            "thresholds.adaptive_toggle",
            default="Adjust thresholds from the living-cat average",
        ))
        self._adaptive_check.setChecked(self._prefs["adaptive_enabled"])
        self._adaptive_check.toggled.connect(self._update_preview)

        self._reference_spin = QDoubleSpinBox()
        self._reference_spin.setRange(0.0, 99.0)
        self._reference_spin.setDecimals(1)
        self._reference_spin.setSingleStep(0.5)
        self._reference_spin.setValue(float(self._prefs["adaptive_reference_avg_sum"]))
        self._reference_spin.valueChanged.connect(self._update_preview)

        self._curve_spin = QDoubleSpinBox()
        self._curve_spin.setRange(0.0, 5.0)
        self._curve_spin.setDecimals(2)
        self._curve_spin.setSingleStep(0.1)
        self._curve_spin.setValue(float(self._prefs["adaptive_curve_strength"]))
        self._curve_spin.valueChanged.connect(self._update_preview)

        grid.addWidget(QLabel(_tr("thresholds.exceptional", default="Exceptional threshold")), 0, 0)
        grid.addWidget(self._exceptional_spin, 0, 1)
        grid.addWidget(QLabel(_tr("thresholds.donation", default="Donation threshold")), 1, 0)
        grid.addWidget(self._donation_spin, 1, 1)
        grid.addWidget(QLabel(_tr("thresholds.donation_top_stat", default="Donation max top stat")), 2, 0)
        grid.addWidget(self._top_stat_spin, 2, 1)
        grid.addWidget(self._planner_trait_check, 3, 0, 1, 2)
        grid.addWidget(self._adaptive_check, 4, 0, 1, 2)
        grid.addWidget(QLabel(_tr("thresholds.reference_average", default="Reference living average")), 5, 0)
        grid.addWidget(self._reference_spin, 5, 1)
        grid.addWidget(QLabel(_tr("thresholds.curve_strength", default="Curve strength")), 6, 0)
        grid.addWidget(self._curve_spin, 6, 1)
        root.addLayout(grid)

        self._current_avg_label = QLabel()
        self._current_avg_label.setWordWrap(True)
        self._current_avg_label.setStyleSheet("color:#9ea4c6;")
        root.addWidget(self._current_avg_label)

        self._preview_label = QLabel()
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("color:#d8d8e8; font-weight:bold;")
        root.addWidget(self._preview_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_btn = QPushButton(_tr("common.cancel", default="Cancel"))
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(_tr("common.ok", default="OK"))
        ok_btn.clicked.connect(self.accept)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)
        root.addLayout(button_row)

        self._adaptive_check.toggled.connect(self._update_adaptive_controls)
        self._update_adaptive_controls(self._adaptive_check.isChecked())
        self._update_preview()

    def _update_adaptive_controls(self, enabled: bool):
        self._reference_spin.setEnabled(enabled)
        self._curve_spin.setEnabled(enabled)

    def _sync_exceptional_floor(self):
        if self._exceptional_spin.value() < self._donation_spin.value():
            self._exceptional_spin.blockSignals(True)
            try:
                self._exceptional_spin.setValue(self._donation_spin.value())
            finally:
                self._exceptional_spin.blockSignals(False)

    def _collect_preferences(self) -> dict:
        return {
            "exceptional_sum_threshold": int(self._exceptional_spin.value()),
            "donation_sum_threshold": int(self._donation_spin.value()),
            "donation_max_top_stat": int(self._top_stat_spin.value()),
            "donation_missing_planner_traits": bool(self._planner_trait_check.isChecked()),
            "adaptive_enabled": bool(self._adaptive_check.isChecked()),
            "adaptive_reference_avg_sum": float(self._reference_spin.value()),
            "adaptive_curve_strength": float(self._curve_spin.value()),
        }

    def _update_preview(self, *_args):
        self._sync_exceptional_floor()
        prefs = _normalize_threshold_preferences(self._collect_preferences())
        exceptional, donation, top_stat, avg_sum = _effective_thresholds_for_cats(prefs, self._cats)
        if self._cats:
            self._current_avg_label.setText(
                _tr(
                    "thresholds.current_average",
                    default="Living cats average base sum: {avg:.1f}",
                    avg=avg_sum,
                )
            )
        else:
            self._current_avg_label.setText(
                _tr(
                    "thresholds.no_save_preview",
                    default="Load a save to preview the curve; the values below will still be saved.",
                )
            )
        if prefs["adaptive_enabled"] and self._cats:
            preview_text = _tr(
                "thresholds.preview",
                default="Effective now: Exceptional >= {exceptional}, Donation <= {donation}, Donation top stat <= {top_stat}",
                exceptional=exceptional,
                donation=donation,
                top_stat=top_stat,
            )
        elif prefs["adaptive_enabled"]:
            preview_text = _tr(
                "thresholds.preview_no_save",
                default="Adaptive mode is on, but there is no save loaded yet.",
            )
        else:
            preview_text = _tr(
                "thresholds.preview_fixed",
                default="Fixed thresholds: Exceptional >= {exceptional}, Donation <= {donation}, Donation top stat <= {top_stat}",
                exceptional=exceptional,
                donation=donation,
                top_stat=top_stat,
            )
        if prefs.get("donation_missing_planner_traits"):
            preview_text += _tr(
                "thresholds.preview.planner_trait_note",
                default=" Cats missing the selected mutation/ability traits will count as donation candidates if they are still under the stat floor.",
            )
        self._preview_label.setText(preview_text)

    def preferences(self) -> dict:
        return _normalize_threshold_preferences(self._collect_preferences())


# ---------------------------------------------------------------------------
# SharedOptimizerSearchSettingsDialog
# ---------------------------------------------------------------------------

class SharedOptimizerSearchSettingsDialog(QDialog):
    def __init__(self, parent=None, settings: dict | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(_tr(
            "menu.settings.optimizer_search_settings.title",
            default="Shared Optimizer Search Settings",
        ))
        self.setMinimumWidth(460)
        self.setStyleSheet(
            "QDialog { background:#0a0a18; }"
            "QLabel { color:#cfcfe0; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:6px 12px; font-size:11px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
            "QSpinBox, QDoubleSpinBox { background:#0d0d1c; color:#ddd; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:3px 6px; }"
        )

        self._settings = _normalize_optimizer_search_settings(settings or _load_optimizer_search_settings())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        desc = QLabel(_tr(
            "menu.settings.optimizer_search_settings.description",
            default="These values control the simulated annealing search used by the room optimizer and Perfect 7 planner.",
        ))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px; color:#a8a8c0;")
        root.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 1000.0)
        self._temperature_spin.setDecimals(1)
        self._temperature_spin.setSingleStep(0.5)
        self._temperature_spin.setValue(float(self._settings["temperature"]))

        self._neighbors_spin = QSpinBox()
        self._neighbors_spin.setRange(1, 5000)
        self._neighbors_spin.setSingleStep(8)
        self._neighbors_spin.setValue(int(self._settings["neighbors"]))

        grid.addWidget(QLabel(_tr("room_optimizer.sa_temperature", default="Temperature:")), 0, 0)
        grid.addWidget(self._temperature_spin, 0, 1)
        _temp_default = QLabel(f"default: {_OPTIMIZER_SEARCH_DEFAULTS['temperature']:.1f}")
        _temp_default.setStyleSheet("color:#5a607a; font-size:11px;")
        grid.addWidget(_temp_default, 0, 2)
        grid.addWidget(QLabel(_tr("room_optimizer.sa_neighbors", default="Neighbors:")), 1, 0)
        grid.addWidget(self._neighbors_spin, 1, 1)
        _neighbors_default = QLabel(f"default: {_OPTIMIZER_SEARCH_DEFAULTS['neighbors']}")
        _neighbors_default.setStyleSheet("color:#5a607a; font-size:11px;")
        grid.addWidget(_neighbors_default, 1, 2)
        root.addLayout(grid)

        note = QLabel(_tr(
            "menu.settings.optimizer_search_settings.note",
            default="Changes take effect the next time either planner runs.",
        ))
        note.setWordWrap(True)
        note.setStyleSheet("color:#9ea4c6;")
        root.addWidget(note)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_btn = QPushButton(_tr("common.cancel", default="Cancel"))
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(_tr("common.ok", default="OK"))
        ok_btn.clicked.connect(self.accept)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)
        root.addLayout(button_row)

    def preferences(self) -> dict:
        return _normalize_optimizer_search_settings({
            "temperature": float(self._temperature_spin.value()),
            "neighbors": int(self._neighbors_spin.value()),
        })


# ---------------------------------------------------------------------------
# SaveSelectorDialog
# ---------------------------------------------------------------------------

class SaveSelectorDialog(QDialog):
    """Startup dialog for picking which save file to load."""

    def __init__(self, saves: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{_tr('app.title')} \u2014 {_tr('save_picker.title')}")
        self.setFixedSize(520, 360)
        self.setStyleSheet(
            "QDialog { background:#0d0d1c; }"
            "QLabel { color:#ccc; }"
            "QListWidget { background:#101023; color:#ddd; border:1px solid #26264a;"
            " font-size:13px; }"
            "QListWidget::item { padding:6px; }"
            "QListWidget::item:selected { background:#1e3060; }"
            "QPushButton { background:#1f5f4a; color:#f2f7f3; border:1px solid #3f8f72;"
            " border-radius:4px; padding:8px 20px; font-size:12px; font-weight:bold; }"
            "QPushButton:hover { background:#26735a; }"
            "QPushButton:disabled { background:#1a1a32; color:#555; border-color:#2a2a4a; }"
        )
        self._selected_path: Optional[str] = None

        vb = QVBoxLayout(self)
        vb.setContentsMargins(16, 16, 16, 16)
        vb.setSpacing(12)

        title = QLabel(_tr("save_picker.title"))
        title.setStyleSheet("color:#ddd; font-size:16px; font-weight:bold;")
        vb.addWidget(title)

        self._list = QListWidget()
        self._list.setIconSize(QSize(60, 20))
        for path in saves:
            name = os.path.basename(path)
            folder = os.path.basename(os.path.dirname(os.path.dirname(path)))
            mtime = os.path.getmtime(path)
            ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{name}  ({folder})  \u2014  {ts}")
            item.setData(Qt.UserRole, path)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _: self._accept())
        vb.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._open_btn = QPushButton(_tr("save_picker.open"))
        self._open_btn.clicked.connect(self._accept)
        self._open_btn.setEnabled(len(saves) > 0)
        btn_row.addWidget(self._open_btn)

        browse_btn = QPushButton(_tr("save_picker.browse"))
        browse_btn.setStyleSheet(
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
        )
        browse_btn.clicked.connect(self._browse)
        btn_row.addWidget(browse_btn)
        vb.addLayout(btn_row)

    def _accept(self):
        cur = self._list.currentItem()
        if cur is not None:
            self._selected_path = cur.data(Qt.UserRole)
            self.accept()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            _tr("dialog.open_save.title"),
            str(Path.home()),
            _tr("dialog.open_save.filter"),
        )
        if path:
            self._selected_path = path
            self.accept()

    @property
    def selected_path(self) -> Optional[str]:
        return self._selected_path
