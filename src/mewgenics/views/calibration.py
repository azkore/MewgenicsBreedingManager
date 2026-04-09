"""CalibrationView — in-app calibration editor for parser-sensitive fields."""

import json
import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStyledItemDelegate, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QSize, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator

from save_parser import Cat, STAT_NAMES
from mewgenics.models.cat_table_model import _SortKeyItem
from mewgenics.utils.calibration import (
    _CALIBRATION_TRAIT_OPTIONS,
    _trait_label_from_value, _normalize_override_gender,
    _normalize_trait_override,
    _load_calibration_data, _save_calibration_data,
    _learn_gender_token_map, _apply_calibration_data,
)
from mewgenics.utils.localization import _tr
from mewgenics.utils.styling import _enforce_min_font_in_widget_tree
from mewgenics.utils.tags import _make_tag_icon, _cat_tags
from mewgenics.utils.paths import _calibration_path


class CalibrationView(QWidget):
    """
    In-app calibration editor for parser-sensitive fields.
    Edits are saved to <save>.calibration.json and applied to app logic.
    """
    calibrationChanged = Signal()

    # Sort order for combo columns (lower = first when ascending)
    _GENDER_SORT    = {"": 0, "male": 1, "female": 2, "?": 3}
    _SEXUALITY_SORT = {"": 0, "straight": 1, "bi": 2, "gay": 3}
    _TRAIT_SORT     = {"": 0, "not": 1, "slightly": 2, "moderately": 3, "highly": 4, "extremely": 5}

    COL_NAME = 0
    COL_STATUS = 1
    COL_TOKEN = 2
    COL_TOKEN_FIELDS = 3
    COL_PARSED_G = 4
    COL_OVR_G = 5
    COL_DEFAULT_SEXUALITY = 6
    COL_OVR_SEXUALITY = 7
    COL_PARSED_AGE = 8
    COL_OVR_AGE = 9
    COL_PARSED_AGG = 10
    COL_OVR_AGG = 11
    COL_PARSED_LIB = 12
    COL_OVR_LIB = 13
    COL_PARSED_INB = 14
    COL_CALC_INB = 15
    COL_OVR_INB = 16
    COL_OVR_STR = 17
    COL_OVR_DEX = 18
    COL_OVR_CON = 19
    COL_OVR_INT = 20
    COL_OVR_SPD = 21
    COL_OVR_CHA = 22
    COL_OVR_LCK = 23

    class _AgeNumericDelegate(QStyledItemDelegate):
        def createEditor(self, parent, option, index):
            editor = QLineEdit(parent)
            # Allow blank (no override) or a non-negative number with up to 3 decimals.
            validator = QRegularExpressionValidator(
                QRegularExpression(r"^$|^\d+(?:\.\d{0,3})?$"),
                editor,
            )
            editor.setValidator(validator)
            return editor

    class _StatDelegate(QStyledItemDelegate):
        def createEditor(self, parent, option, index):
            editor = QLineEdit(parent)
            # Allow blank or integer 0-20
            validator = QRegularExpressionValidator(
                QRegularExpression(r"^$|^([0-9]|1[0-9]|20)$"),
                editor,
            )
            editor.setValidator(validator)
            return editor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget { background:#0a0a18; }"
            "QLabel { color:#bbb; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:6px 10px; font-size:11px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
            "QComboBox { background:#1a1a32; color:#ddd; border:1px solid #2a2a4a; padding:2px 6px; }"
            "QComboBox QAbstractItemView { background:#101023; color:#ddd; selection-background-color:#252545; }"
            "QTableWidget { background:#101023; color:#ddd; border:1px solid #26264a; }"
            "QHeaderView::section { background:#151532; color:#7d8bb0; border:none; padding:4px; font-weight:bold; }"
        )
        self._save_path: Optional[str] = None
        self._cats: list[Cat] = []
        self._row_cat: list[Cat] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color:#ddd; font-size:18px; font-weight:bold;")
        root.addWidget(self._title_label)

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet("color:#8d8da8; font-size:11px;")
        root.addWidget(self._desc_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._search_label = QLabel()
        self._search_label.setStyleSheet("color:#888; font-size:11px;")
        filter_row.addWidget(self._search_label)
        self._search_input = QLineEdit()
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setStyleSheet(
            "QLineEdit { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 8px; }"
        )
        self._search_input.setToolTip(_tr("calibration.search.tooltip", default="Filter cats by name"))
        self._search_input.textChanged.connect(self._apply_search_filter)
        filter_row.addWidget(self._search_input, 1)
        root.addLayout(filter_row)

        actions = QHBoxLayout()
        self._save_btn = QPushButton()
        self._save_btn.setToolTip(_tr("calibration.save.tooltip", default="Save calibration overrides to disk"))
        self._reload_btn = QPushButton()
        self._reload_btn.setToolTip(_tr("calibration.reload.tooltip", default="Reload calibration data from disk"))
        self._export_btn = QPushButton()
        self._export_btn.setToolTip(_tr("calibration.export.tooltip", default="Export gender overrides as CSV"))
        self._import_btn = QPushButton()
        self._import_btn.setToolTip(_tr("calibration.import.tooltip", default="Import gender overrides from CSV"))
        self._clear_overrides_btn = QPushButton()
        self._clear_overrides_btn.setToolTip(_tr("calibration.clear_overrides.tooltip", default="Remove all calibration overrides"))
        self._clear_overrides_btn.setStyleSheet(
            "QPushButton { background:#3a2a2a; color:#e0a0a0; border:1px solid #5a3a3a; "
            "border-radius:4px; padding:6px 10px; font-size:11px; }"
            "QPushButton:hover { background:#4a3a3a; color:#ffb0b0; }"
        )
        self._status = QLabel("")
        self._status.setStyleSheet("color:#8d8da8; font-size:11px;")
        actions.addWidget(self._save_btn)
        actions.addWidget(self._reload_btn)
        actions.addWidget(self._export_btn)
        actions.addWidget(self._import_btn)
        actions.addWidget(self._clear_overrides_btn)
        actions.addSpacing(16)

        self._bulk_label = QLabel()
        self._bulk_label.setStyleSheet("color:#888; font-size:11px;")
        actions.addWidget(self._bulk_label)

        self._bulk_sexuality_combo = QComboBox()
        self._bulk_sexuality_combo.setFixedWidth(100)
        self._bulk_sexuality_combo.setStyleSheet(
            "QComboBox { background:#1a1a32; color:#ddd; border:1px solid #2a2a4a; padding:2px 6px; }"
            "QComboBox QAbstractItemView { background:#101023; color:#ddd; selection-background-color:#252545; }"
        )
        actions.addWidget(self._bulk_sexuality_combo)

        self._bulk_apply_btn = QPushButton()
        self._bulk_apply_btn.setStyleSheet(
            "QPushButton { background:#2a3a2a; color:#aaa; border:1px solid #3a5a3a; "
            "border-radius:4px; padding:4px 10px; font-size:10px; }"
            "QPushButton:hover { background:#3a4a3a; color:#ddd; }"
        )
        self._bulk_apply_btn.setToolTip(_tr("calibration.bulk_apply.tooltip", default="Apply selected sexuality to all checked cats"))
        self._bulk_apply_btn.clicked.connect(self._on_bulk_apply_sexuality)
        actions.addWidget(self._bulk_apply_btn)

        self._deselect_btn = QPushButton(_tr("calibration.deselect_all", default="Deselect All"))
        self._deselect_btn.setToolTip(_tr("calibration.deselect.tooltip", default="Deselect all checked cats"))
        self._deselect_btn.setStyleSheet(
            "QPushButton { background:#1a1a32; color:#888; border:1px solid #2a2a4a; "
            "border-radius:4px; padding:4px 10px; font-size:10px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
        )
        actions.addWidget(self._deselect_btn)

        actions.addStretch()
        actions.addWidget(self._status)
        root.addLayout(actions)

        self._table = QTableWidget(0, 24)
        self._table.setIconSize(QSize(60, 20))
        self._table.setHorizontalHeaderLabels([
            "Name", "Status", "Gender\nToken", "Pre-G\nU32s", "Parsed\nG", "Override\nG",
            "Default\nSexuality", "Sexuality",
            "Parsed\nAge", "Override\nAge",
            "Parsed\nAgg", "Override\nAgg",
            "Parsed\nLibido", "Override\nLibido",
            "Parsed\nInbr", "Calc\nInbr", "Override\nInbr",
            "STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Allow Ctrl-click for disjoint row picks and Shift-click for ranges.
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self._table.setItemDelegateForColumn(self.COL_OVR_AGE, self._AgeNumericDelegate(self._table))
        for stat_col in (self.COL_OVR_STR, self.COL_OVR_DEX, self.COL_OVR_CON,
                         self.COL_OVR_INT, self.COL_OVR_SPD, self.COL_OVR_CHA, self.COL_OVR_LCK):
            self._table.setItemDelegateForColumn(stat_col, self._StatDelegate(self._table))
        hh = self._table.horizontalHeader()
        hh.setMinimumSectionSize(40)
        hh.setDefaultAlignment(Qt.AlignCenter)
        hh.setMinimumHeight(36)
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.Interactive)
        self._table.setColumnWidth(self.COL_NAME, 140)
        hh.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        self._table.setColumnWidth(self.COL_STATUS, 92)
        hh.setSectionResizeMode(self.COL_TOKEN, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_TOKEN_FIELDS, QHeaderView.ResizeToContents)
        for col in (self.COL_PARSED_G, self.COL_OVR_G):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)
            self._table.setColumnWidth(col, 68)
        hh.setSectionResizeMode(self.COL_DEFAULT_SEXUALITY, QHeaderView.Interactive)
        self._table.setColumnWidth(self.COL_DEFAULT_SEXUALITY, 80)
        hh.setSectionResizeMode(self.COL_OVR_SEXUALITY, QHeaderView.Interactive)
        self._table.setColumnWidth(self.COL_OVR_SEXUALITY, 80)
        for col in (
            self.COL_PARSED_AGE, self.COL_OVR_AGE,
            self.COL_PARSED_AGG, self.COL_OVR_AGG,
            self.COL_PARSED_LIB, self.COL_OVR_LIB,
            self.COL_PARSED_INB, self.COL_CALC_INB, self.COL_OVR_INB,
        ):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)
            self._table.setColumnWidth(col, 76)
        for col in (self.COL_OVR_AGG, self.COL_OVR_LIB, self.COL_OVR_INB):
            self._table.setColumnWidth(col, 110)
        for stat_col in (self.COL_OVR_STR, self.COL_OVR_DEX, self.COL_OVR_CON,
                         self.COL_OVR_INT, self.COL_OVR_SPD, self.COL_OVR_CHA, self.COL_OVR_LCK):
            hh.setSectionResizeMode(stat_col, QHeaderView.Interactive)
            self._table.setColumnWidth(stat_col, 50)
        self._table.setSortingEnabled(True)
        root.addWidget(self._table, 1)

        self.retranslate_ui()
        self._save_btn.clicked.connect(self._save_clicked)
        self._reload_btn.clicked.connect(self._reload_clicked)
        self._export_btn.clicked.connect(self._export_clicked)
        self._import_btn.clicked.connect(self._import_clicked)
        self._clear_overrides_btn.clicked.connect(self._clear_overrides_clicked)
        self._deselect_btn.clicked.connect(self._table.clearSelection)

    def retranslate_ui(self):
        self._title_label.setText(_tr("calibration.title"))
        self._desc_label.setText(_tr("calibration.description"))
        self._save_btn.setText(_tr("calibration.save"))
        self._reload_btn.setText(_tr("calibration.reload"))
        self._export_btn.setText(_tr("calibration.export"))
        self._import_btn.setText(_tr("calibration.import"))
        self._clear_overrides_btn.setText(_tr("calibration.clear_overrides", default="Clear Overrides"))
        self._deselect_btn.setText(_tr("calibration.deselect_all", default="Deselect All"))
        self._bulk_label.setText(_tr("calibration.bulk_edit_selected"))
        self._search_label.setText(_tr("calibration.search"))
        self._search_input.setPlaceholderText(_tr("calibration.search_placeholder"))
        current_value = self._bulk_sexuality_combo.currentData()
        self._bulk_sexuality_combo.blockSignals(True)
        self._bulk_sexuality_combo.clear()
        self._bulk_sexuality_combo.addItem(_tr("calibration.sexuality.clear", default="— clear —"), "")
        self._bulk_sexuality_combo.addItem(_tr("calibration.sexuality.straight"), "straight")
        self._bulk_sexuality_combo.addItem(_tr("calibration.sexuality.gay"), "gay")
        self._bulk_sexuality_combo.addItem(_tr("calibration.sexuality.bi"), "bi")
        index = self._bulk_sexuality_combo.findData(current_value)
        if index >= 0:
            self._bulk_sexuality_combo.setCurrentIndex(index)
        self._bulk_sexuality_combo.blockSignals(False)
        self._bulk_apply_btn.setText(_tr("calibration.apply_sexuality"))
        self._table.setHorizontalHeaderLabels([
            _tr("calibration.table.name"),
            _tr("calibration.table.status"),
            _tr("calibration.table.gender_token"),
            _tr("calibration.table.pre_gender_u32"),
            _tr("calibration.table.parsed_gender"),
            _tr("calibration.table.override_gender"),
            _tr("calibration.table.default_sexuality"),
            _tr("calibration.table.sexuality"),
            _tr("calibration.table.parsed_age"),
            _tr("calibration.table.override_age"),
            _tr("calibration.table.parsed_agg"),
            _tr("calibration.table.override_agg"),
            _tr("calibration.table.parsed_libido"),
            _tr("calibration.table.override_libido"),
            _tr("calibration.table.parsed_inbr"),
            _tr("calibration.table.calc_inbr", default="Calc\nInbr"),
            _tr("calibration.table.override_inbr"),
            "STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK",
        ])
        if self._save_path and self._cats:
            self.set_context(self._save_path, self._cats)
        _enforce_min_font_in_widget_tree(self)

    @staticmethod
    def _fmt(v) -> str:
        if v is None:
            return ""
        try:
            return f"{float(v):.3f}".rstrip("0").rstrip(".")
        except Exception:
            return str(v)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    @staticmethod
    def _fmt_gender_token_fields(cat: Cat) -> str:
        vals = getattr(cat, "gender_token_fields", None)
        if not vals:
            return ""
        return ", ".join(str(int(v)) for v in vals)

    @staticmethod
    def _editable_item(text: str) -> QTableWidgetItem:
        return QTableWidgetItem(text)

    @staticmethod
    def _get_text_item(table: QTableWidget, row: int, col: int) -> str:
        w = table.cellWidget(row, col)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        it = table.item(row, col)
        return (it.text().strip() if it is not None else "")

    @staticmethod
    def _gender_combo(value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(["", "male", "female", "?"])
        idx = combo.findText((value or "").strip().lower(), Qt.MatchFixedString)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        return combo

    @staticmethod
    def _make_sort_item(sort_key: int) -> "_SortKeyItem":
        item = _SortKeyItem()
        item.setData(Qt.UserRole, sort_key)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _sexuality_combo(value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("", "")
        combo.addItem(_tr("calibration.sexuality.bi"), "bi")
        combo.addItem(_tr("calibration.sexuality.gay"), "gay")
        combo.addItem(_tr("calibration.sexuality.straight"), "straight")
        idx = combo.findData((value or "").strip().lower(), Qt.UserRole, Qt.MatchFixedString)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        return combo

    @staticmethod
    def _trait_combo(options: tuple[str, ...], value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems([""] + list(options))
        idx = combo.findText((value or "").strip().lower(), Qt.MatchFixedString)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        return combo

    @staticmethod
    def _get_optional_float(table: QTableWidget, row: int, col: int):
        txt = CalibrationView._get_text_item(table, row, col)
        if txt == "":
            return None
        try:
            return float(txt)
        except Exception:
            return None

    def set_context(self, save_path: str, cats: list[Cat]):
        self._save_path = save_path
        self._cats = sorted([c for c in cats if c.status != "Gone"], key=lambda c: (c.name or "").lower())
        self._row_cat = []

        data = _load_calibration_data(save_path)
        overrides = data.get("overrides", {}) if isinstance(data, dict) else {}
        if not isinstance(overrides, dict):
            overrides = {}

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._cats))
        for row, cat in enumerate(self._cats):
            self._row_cat.append(cat)
            uid = (cat.unique_id or "").strip().lower()
            ov = overrides.get(uid) if isinstance(overrides.get(uid), dict) else {}

            name_item = self._readonly_item(cat.name or "?")
            name_item.setData(Qt.UserRole, cat)
            icon = _make_tag_icon(_cat_tags(cat), dot_size=10, spacing=3)
            if not icon.isNull():
                name_item.setIcon(icon)
            self._table.setItem(row, self.COL_NAME, name_item)
            self._table.setItem(row, self.COL_STATUS, self._readonly_item(cat.status))
            self._table.setItem(row, self.COL_TOKEN, self._readonly_item(getattr(cat, "gender_token", "") or ""))
            self._table.setItem(row, self.COL_TOKEN_FIELDS, self._readonly_item(self._fmt_gender_token_fields(cat)))
            self._table.setItem(row, self.COL_PARSED_G, self._readonly_item((getattr(cat, "parsed_gender", cat.gender) or "?")))
            g_combo = self._gender_combo(str(ov.get("gender", "") or ""))
            g_sort = self._make_sort_item(self._GENDER_SORT.get((ov.get("gender") or "").lower(), 0))
            self._table.setCellWidget(row, self.COL_OVR_G, g_combo)
            self._table.setItem(row, self.COL_OVR_G, g_sort)
            g_combo.currentIndexChanged.connect(lambda _, c=g_combo, it=g_sort: it.setData(Qt.UserRole, self._GENDER_SORT.get(c.currentText().lower(), 0)))

            self._table.setItem(row, self.COL_DEFAULT_SEXUALITY, self._readonly_item(getattr(cat, "parsed_sexuality", "straight")))
            sex_val = str(ov.get("sexuality", "") or "")
            sex_combo = self._sexuality_combo(sex_val)
            sex_sort = self._make_sort_item(self._SEXUALITY_SORT.get(sex_val, 0))
            self._table.setCellWidget(row, self.COL_OVR_SEXUALITY, sex_combo)
            self._table.setItem(row, self.COL_OVR_SEXUALITY, sex_sort)
            sex_combo.currentIndexChanged.connect(lambda _, c=sex_combo, it=sex_sort: it.setData(Qt.UserRole, self._SEXUALITY_SORT.get(c.currentData() or "", 0)))

            self._table.setItem(row, self.COL_PARSED_AGE, self._readonly_item(self._fmt(getattr(cat, "parsed_age", None))))
            self._table.setItem(row, self.COL_OVR_AGE, self._editable_item(self._fmt(ov.get("age"))))
            self._table.setItem(row, self.COL_PARSED_AGG, self._readonly_item(self._fmt(getattr(cat, "parsed_aggression", None))))
            agg_val = _trait_label_from_value("aggression", ov.get("aggression"))
            agg_combo = self._trait_combo(_CALIBRATION_TRAIT_OPTIONS["aggression"], agg_val)
            agg_sort = self._make_sort_item(self._TRAIT_SORT.get(agg_val, 0))
            self._table.setCellWidget(row, self.COL_OVR_AGG, agg_combo)
            self._table.setItem(row, self.COL_OVR_AGG, agg_sort)
            agg_combo.currentIndexChanged.connect(lambda _, c=agg_combo, it=agg_sort: it.setData(Qt.UserRole, self._TRAIT_SORT.get(c.currentText(), 0)))

            self._table.setItem(row, self.COL_PARSED_LIB, self._readonly_item(self._fmt(getattr(cat, "parsed_libido", None))))
            lib_val = _trait_label_from_value("libido", ov.get("libido"))
            lib_combo = self._trait_combo(_CALIBRATION_TRAIT_OPTIONS["libido"], lib_val)
            lib_sort = self._make_sort_item(self._TRAIT_SORT.get(lib_val, 0))
            self._table.setCellWidget(row, self.COL_OVR_LIB, lib_combo)
            self._table.setItem(row, self.COL_OVR_LIB, lib_sort)
            lib_combo.currentIndexChanged.connect(lambda _, c=lib_combo, it=lib_sort: it.setData(Qt.UserRole, self._TRAIT_SORT.get(c.currentText(), 0)))

            self._table.setItem(row, self.COL_PARSED_INB, self._readonly_item(self._fmt(getattr(cat, "parsed_inbredness", None))))
            # Computed COI from ancestry (set by CatTableModel.load)
            calc_inb = cat.inbredness if cat.inbredness != cat.parsed_inbredness else None
            calc_label = _trait_label_from_value("inbredness", calc_inb) if calc_inb is not None else ""
            calc_text = f"{calc_inb:.3f} ({calc_label})" if calc_inb is not None else "—"
            self._table.setItem(row, self.COL_CALC_INB, self._readonly_item(calc_text))
            inb_val = _trait_label_from_value("inbredness", ov.get("inbredness"))
            inb_combo = self._trait_combo(_CALIBRATION_TRAIT_OPTIONS["inbredness"], inb_val)
            inb_sort = self._make_sort_item(self._TRAIT_SORT.get(inb_val, 0))
            self._table.setCellWidget(row, self.COL_OVR_INB, inb_combo)
            self._table.setItem(row, self.COL_OVR_INB, inb_sort)
            inb_combo.currentIndexChanged.connect(lambda _, c=inb_combo, it=inb_sort: it.setData(Qt.UserRole, self._TRAIT_SORT.get(c.currentText(), 0)))

            # Add base stats override columns
            for i, stat_name in enumerate(STAT_NAMES):
                stat_col = self.COL_OVR_STR + i
                override_val = ov.get("base_stats", {}).get(stat_name, "")
                current_val = cat.base_stats.get(stat_name, 0)
                # Show current value in background, allow override
                item = self._editable_item(str(override_val) if override_val != "" else "")
                item.setToolTip(f"Current: {current_val}")
                self._table.setItem(row, stat_col, item)

        self._table.setSortingEnabled(True)
        self._status.setText(_tr("calibration.status.alive_cats", count=len(self._cats)))
        self._apply_search_filter()

    def _apply_search_filter(self, text: Optional[str] = None):
        needle = (text if text is not None else self._search_input.text()).strip().lower()
        for row in range(self._table.rowCount()):
            if not needle:
                self._table.setRowHidden(row, False)
                continue
            fields = [
                self._get_text_item(self._table, row, self.COL_NAME),
                self._get_text_item(self._table, row, self.COL_STATUS),
                self._get_text_item(self._table, row, self.COL_TOKEN),
                self._get_text_item(self._table, row, self.COL_TOKEN_FIELDS),
                self._get_text_item(self._table, row, self.COL_PARSED_G),
                self._get_text_item(self._table, row, self.COL_OVR_G),
                self._get_text_item(self._table, row, self.COL_DEFAULT_SEXUALITY),
                self._get_text_item(self._table, row, self.COL_OVR_SEXUALITY),
            ]
            match = any(needle in (field or "").lower() for field in fields)
            self._table.setRowHidden(row, not match)

    def _reload_clicked(self):
        if not self._save_path:
            self._status.setText(_tr("calibration.status.no_save_loaded"))
            return
        self.set_context(self._save_path, self._cats)
        self._status.setText(_tr("calibration.status.reloaded"))

    def _collect_calibration_data(self) -> dict:
        overrides: dict[str, dict] = {}
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, self.COL_NAME)
            cat = name_item.data(Qt.UserRole) if name_item else None
            if cat is None:
                continue
            uid = (cat.unique_id or "").strip().lower()
            if not uid:
                continue

            g = _normalize_override_gender(self._get_text_item(self._table, row, self.COL_OVR_G))
            age = self._get_optional_float(self._table, row, self.COL_OVR_AGE)
            agg = _normalize_trait_override("aggression", self._get_text_item(self._table, row, self.COL_OVR_AGG))
            lib = _normalize_trait_override("libido", self._get_text_item(self._table, row, self.COL_OVR_LIB))
            inb = _normalize_trait_override("inbredness", self._get_text_item(self._table, row, self.COL_OVR_INB))
            sexuality_widget = self._table.cellWidget(row, self.COL_OVR_SEXUALITY)
            sexuality_raw = sexuality_widget.currentData() if isinstance(sexuality_widget, QComboBox) else ""
            sexuality = sexuality_raw if sexuality_raw in ("bi", "gay", "straight") else ""

            # Collect base stats overrides
            base_stats = {}
            for i, stat_name in enumerate(STAT_NAMES):
                stat_col = self.COL_OVR_STR + i
                txt = self._get_text_item(self._table, row, stat_col).strip()
                if txt:
                    try:
                        val = int(txt)
                        if 0 <= val <= 20:
                            base_stats[stat_name] = val
                    except ValueError:
                        pass

            if g or age is not None or agg or lib or inb or sexuality or base_stats:
                ov = {"name": cat.name}
                if g:
                    ov["gender"] = g
                if age is not None:
                    ov["age"] = age
                if agg:
                    ov["aggression"] = agg
                if lib:
                    ov["libido"] = lib
                if inb:
                    ov["inbredness"] = inb
                if sexuality:
                    ov["sexuality"] = sexuality
                if base_stats:
                    ov["base_stats"] = base_stats
                overrides[uid] = ov

        return {
            "version": 1,
            "overrides": overrides,
            "gender_token_map": _learn_gender_token_map(self._cats, overrides),
        }

    def _save_clicked(self):
        if not self._save_path:
            self._status.setText(_tr("calibration.status.no_save_loaded"))
            return

        data = self._collect_calibration_data()
        overrides = data.get("overrides", {}) if isinstance(data, dict) else {}
        if not _save_calibration_data(self._save_path, data):
            self._status.setText(_tr("calibration.status.save_failed"))
            return

        explicit, token_applied, _ = _apply_calibration_data(data, self._cats)
        self._status.setText(
            _tr(
                "calibration.status.saved",
                overrides=len(overrides),
                applied=explicit,
                hints=len(data["gender_token_map"]),
                token=token_applied,
            )
        )
        self.calibrationChanged.emit()

    def _export_clicked(self):
        if not self._save_path:
            self._status.setText(_tr("calibration.status.no_save_loaded"))
            return
        default_path = _calibration_path(self._save_path)
        path, _ = QFileDialog.getSaveFileName(
            self,
            _tr("calibration.dialog.export.title"),
            default_path,
            _tr("calibration.dialog.filter"),
        )
        if not path:
            return
        data = self._collect_calibration_data()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
            self._status.setText(_tr("calibration.status.exported", name=os.path.basename(path)))
        except Exception:
            self._status.setText(_tr("calibration.status.export_failed"))

    def _import_clicked(self):
        if not self._save_path:
            self._status.setText(_tr("calibration.status.no_save_loaded"))
            return
        start = os.path.dirname(_calibration_path(self._save_path))
        path, _ = QFileDialog.getOpenFileName(
            self,
            _tr("calibration.dialog.import.title"),
            start,
            _tr("calibration.dialog.filter"),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._status.setText(_tr("calibration.status.read_failed"))
            return
        if not isinstance(data, dict):
            self._status.setText(_tr("calibration.status.invalid_format"))
            return
        overrides = data.get("overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        token_map = data.get("gender_token_map", {})
        if not isinstance(token_map, dict):
            token_map = {}
        normalized = {
            "version": int(data.get("version", 1) or 1),
            "overrides": overrides,
            "gender_token_map": token_map or _learn_gender_token_map(self._cats, overrides),
        }
        if not _save_calibration_data(self._save_path, normalized):
            self._status.setText(_tr("calibration.status.import_failed"))
            return
        explicit, token_applied, _ = _apply_calibration_data(normalized, self._cats)
        self.set_context(self._save_path, self._cats)
        self._status.setText(
            _tr("calibration.status.imported", applied=explicit, token=token_applied, name=os.path.basename(path))
        )
        self.calibrationChanged.emit()

    def _clear_overrides_clicked(self):
        """Clear all manual calibration overrides for all cats."""
        if not self._cats:
            self._status.setText(_tr("calibration.status.no_save_loaded"))
            return

        reply = QMessageBox.question(
            self,
            _tr("calibration.confirm_clear_title", default="Clear All Overrides?"),
            _tr(
                "calibration.confirm_clear_message",
                default="This will clear all manual calibration overrides (age, aggression, libido, inbreeding, stats, sexuality) for all cats. This cannot be undone until you reload. Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Wipe persisted overrides so set_context reloads clean
        if self._save_path:
            cal_data = _load_calibration_data(self._save_path)
            cal_data["overrides"] = {}
            _save_calibration_data(self._save_path, cal_data)

        # Reset cat attributes to parsed values
        for cat in self._cats:
            cat.age = cat.parsed_age
            cat.aggression = cat.parsed_aggression
            cat.libido = cat.parsed_libido
            cat.inbredness = cat.parsed_inbredness
            cat.base_stats = dict(cat.parsed_stats) if cat.parsed_stats else {}
            cat.sexuality = cat.parsed_sexuality

        # Refresh the UI
        self.set_context(self._save_path, self._cats)
        self._status.setText(_tr("calibration.status.overrides_cleared"))
        self.calibrationChanged.emit()

    def _on_bulk_apply_sexuality(self):
        """Apply sexuality to all selected rows."""
        selected_rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not selected_rows:
            self._status.setText(_tr("calibration.status.select_rows"))
            return

        sexuality = str(self._bulk_sexuality_combo.currentData() or "")
        sm = self._table.selectionModel()
        sm.blockSignals(True)
        for row in selected_rows:
            widget = self._table.cellWidget(row, self.COL_OVR_SEXUALITY)
            if isinstance(widget, QComboBox):
                widget.blockSignals(True)
                idx = widget.findData(sexuality)
                widget.setCurrentIndex(idx if idx >= 0 else 0)
                widget.blockSignals(False)
        sm.blockSignals(False)

        self._save_clicked()
        sexuality_label = _tr("calibration.sexuality.clear", default="— clear —") if not sexuality else _tr(f"calibration.sexuality.{sexuality}")
        self._status.setText(
            _tr(
                "calibration.status.applied",
                sexuality=sexuality_label,
                count=len(selected_rows),
            )
        )
