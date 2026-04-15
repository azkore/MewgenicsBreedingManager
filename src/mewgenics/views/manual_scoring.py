"""ManualScoringView — configurable point-based cat scoring and triage."""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QHeaderView,
    QAbstractItemView, QSplitter, QLineEdit, QSpinBox,
    QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QPushButton, QToolButton, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush

from save_parser import Cat, ROOM_KEYS
from mewgenics.utils.localization import _tr, ROOM_DISPLAY
from mewgenics.utils.config import _load_ui_state, _save_ui_state
from mewgenics.utils.cat_analysis import _cat_base_sum
from mewgenics.utils.calibration import _trait_label_from_value
from mewgenics.utils.abilities import _ability_tip, _mutation_display_name


# ---------------------------------------------------------------------------
# Pure scoring function (no Qt)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "stat_weight": 1,
    "desired_mutations": [],
    "desired_mutation_weights": {},   # mutation_name -> int  (per-mutation override)
    "desired_use_individual": False,
    "desired_default_weight": 1,
    "undesired_mutations": [],
    "undesired_mutation_weights": {},
    "undesired_use_individual": False,
    "undesired_default_weight": -5,
    "inbredness_weights": {
        "not": 2, "slightly": 0, "moderately": -1,
        "highly": -10, "extremely": -10,
    },
    "libido_weights": {"high": 1, "average": 0, "low": -10},
    "aggression_weights": {"high": 1, "average": 0, "low": -1},
    "passive_weight": 1,
    "extra_spell_weight": 0,
    "sexuality_weights": {"straight": 0, "bi": -10, "gay": -10},
}


def compute_cat_score(cat, config: dict) -> tuple[int, dict[str, int]]:
    """Return (total_score, breakdown_dict) for a cat given scoring config."""
    breakdown: dict[str, int] = {}

    # Stats
    breakdown["stats"] = config.get("stat_weight", 1) * _cat_base_sum(cat)

    # Desired mutations
    desired = set(config.get("desired_mutations", []))
    use_individual_d = config.get("desired_use_individual", False)
    per_weights_d = config.get("desired_mutation_weights", {})
    default_d = config.get("desired_default_weight", 1)
    d_score = 0
    for m in (cat.mutations or []):
        if m in desired:
            d_score += per_weights_d.get(m, default_d) if use_individual_d else default_d
    breakdown["desired"] = d_score

    # Undesired mutations
    undesired = set(config.get("undesired_mutations", []))
    use_individual_u = config.get("undesired_use_individual", False)
    per_weights_u = config.get("undesired_mutation_weights", {})
    default_u = config.get("undesired_default_weight", -5)
    u_score = 0
    for m in (cat.mutations or []):
        if m in undesired:
            u_score += per_weights_u.get(m, default_u) if use_individual_u else default_u
    breakdown["undesired"] = u_score

    # Inbredness
    inb_label = _trait_label_from_value("inbredness", cat.inbredness) if cat.inbredness is not None else ""
    inb_weights = config.get("inbredness_weights", {})
    breakdown["inbredness"] = inb_weights.get(inb_label, 0)

    # Libido
    lib_label = _trait_label_from_value("libido", cat.libido) if cat.libido is not None else ""
    lib_weights = config.get("libido_weights", {})
    breakdown["libido"] = lib_weights.get(lib_label, 0)

    # Aggression
    agg_label = _trait_label_from_value("aggression", cat.aggression) if cat.aggression is not None else ""
    agg_weights = config.get("aggression_weights", {})
    breakdown["aggression"] = agg_weights.get(agg_label, 0)

    # Passives
    breakdown["passives"] = config.get("passive_weight", 1) * len(cat.passive_abilities or [])

    # Extra spells (abilities beyond the first)
    n_abilities = len(cat.abilities or [])
    breakdown["spells"] = config.get("extra_spell_weight", 0) * max(0, n_abilities - 1)

    # Sexuality
    sex_weights = config.get("sexuality_weights", {})
    breakdown["sexuality"] = sex_weights.get(getattr(cat, "sexuality", ""), 0)

    total = sum(breakdown.values())
    return total, breakdown


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

_BREAKDOWN_KEYS = ["stats", "desired", "undesired", "inbredness", "libido", "aggression", "passives", "spells", "sexuality"]
_BREAKDOWN_LABELS = ["Stats", "Desired", "Undes.", "Inbred", "Libido", "Aggr", "Passives", "Spells", "Sexuality"]

_COL_NAME = 0
_COL_ROOM = 1
_COL_TOTAL = 2
_COL_FIRST_BREAKDOWN = 3
_NUM_COLS = _COL_FIRST_BREAKDOWN + len(_BREAKDOWN_KEYS)

_HEADER_LABELS = ["Name", "Room", "Score"] + _BREAKDOWN_LABELS


# ---------------------------------------------------------------------------
# Reusable mutation selector widget
# ---------------------------------------------------------------------------

class _MutationSelector(QWidget):
    """Collapsible mutation checklist with blanket or per-mutation weights."""

    def __init__(self, title: str, default_weight: int, parent_view: "ManualScoringView"):
        super().__init__()
        self._parent_view = parent_view
        self._default_weight = default_weight
        self._suppress = False
        # Per-mutation spinbox widgets, keyed by raw mutation name.
        self._per_spins: dict[str, QSpinBox] = {}

        vb = QVBoxLayout(self)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(4)

        # Toggle button
        self._toggle = QToolButton()
        self._toggle.setText(f"{title} (0 selected) \u25BC")
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._on_toggled)
        self._title = title
        vb.addWidget(self._toggle)

        # Collapsible body
        self._body = QWidget()
        body_vb = QVBoxLayout(self._body)
        body_vb.setContentsMargins(0, 0, 0, 0)
        body_vb.setSpacing(4)

        # Weight mode toggle
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        lbl = QLabel("Default weight:")
        lbl.setMinimumWidth(100)
        mode_row.addWidget(lbl)
        self._spin_default = QSpinBox()
        self._spin_default.setRange(-99, 99)
        self._spin_default.setValue(default_weight)
        self._spin_default.valueChanged.connect(self._on_changed)
        mode_row.addWidget(self._spin_default)
        mode_row.addStretch()
        body_vb.addLayout(mode_row)

        self._chk_individual = QCheckBox("Set weight per mutation")
        self._chk_individual.toggled.connect(self._on_individual_toggled)
        body_vb.addWidget(self._chk_individual)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter mutations...")
        self._search.textChanged.connect(self._filter_list)
        body_vb.addWidget(self._search)

        # Mutation list (items are rows with checkbox + optional per-mutation spinbox)
        self._list = QListWidget()
        self._list.setMinimumHeight(250)
        self._list.setMaximumHeight(400)
        self._list.itemChanged.connect(self._on_item_changed)
        body_vb.addWidget(self._list)

        # Bulk buttons
        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton("Clear All")
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        body_vb.addLayout(btn_row)

        self._body.hide()
        vb.addWidget(self._body)

    # -- Public API --

    def rebuild(self, all_mutations: list[str], prev_checked: set[str],
                prev_weights: dict[str, int]):
        """Rebuild list items from the set of all mutation names."""
        self._suppress = True
        self._list.clear()
        self._per_spins.clear()
        for m in all_mutations:
            display = _mutation_display_name(m)
            tip = _ability_tip(m)
            label = f"{display}  —  {tip}" if tip else display
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, m)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if m in prev_checked else Qt.Unchecked)
            if tip:
                item.setToolTip(tip)
            self._list.addItem(item)
        self._suppress = False
        self._update_toggle_text()

    def get_checked(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
        ]

    def get_per_weights(self) -> dict[str, int]:
        """Return per-mutation weights for checked mutations."""
        result = {}
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                name = item.data(Qt.UserRole)
                widget = self._list.itemWidget(item)
                if widget is not None:
                    spin = widget.findChild(QSpinBox)
                    if spin is not None:
                        result[name] = spin.value()
        return result

    def use_individual(self) -> bool:
        return self._chk_individual.isChecked()

    def default_weight(self) -> int:
        return self._spin_default.value()

    def set_state(self, *, use_individual: bool, default_weight: int,
                  per_weights: dict[str, int]):
        """Restore state from saved config."""
        self._suppress = True
        self._spin_default.setValue(default_weight)
        self._chk_individual.setChecked(use_individual)
        self._suppress = False
        # Per-weights are applied after rebuild via _apply_per_weights
        self._saved_per_weights = per_weights

    def apply_per_weights(self):
        """Apply saved per-weights after rebuild has populated items."""
        weights = getattr(self, "_saved_per_weights", {})
        if not weights:
            return
        if self._chk_individual.isChecked():
            self._show_per_spins()
            for i in range(self._list.count()):
                item = self._list.item(i)
                name = item.data(Qt.UserRole)
                if name in weights:
                    widget = self._list.itemWidget(item)
                    if widget is not None:
                        spin = widget.findChild(QSpinBox)
                        if spin is not None:
                            spin.setValue(weights[name])

    def reset(self):
        self._suppress = True
        self._spin_default.setValue(self._default_weight)
        self._chk_individual.setChecked(False)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Unchecked)
        self._suppress = False
        self._hide_per_spins()
        self._update_toggle_text()

    # -- Internals --

    def _on_toggled(self, expanded: bool):
        self._body.setVisible(expanded)
        self._update_toggle_text()

    def _on_individual_toggled(self, checked: bool):
        if checked:
            self._show_per_spins()
        else:
            self._hide_per_spins()
        self._on_changed()

    def _show_per_spins(self):
        """Attach per-mutation QSpinBox widgets to each list item."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if self._list.itemWidget(item) is not None:
                continue
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(2, 0, 2, 0)
            row.setSpacing(4)
            chk = QCheckBox()
            chk.setChecked(item.checkState() == Qt.Checked)
            chk.toggled.connect(lambda checked, it=item: self._sync_check_from_widget(it, checked))
            row.addWidget(chk)
            lbl = QLabel(item.text())
            lbl.setStyleSheet("color:#ccc;")
            row.addWidget(lbl, 1)
            spin = QSpinBox()
            spin.setRange(-99, 99)
            spin.setValue(self._spin_default.value())
            spin.setFixedWidth(60)
            spin.valueChanged.connect(self._on_changed)
            row.addWidget(spin)
            self._list.setItemWidget(item, w)
            # Disable the built-in checkbox since the widget checkbox takes over
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            item.setText("")
            item.setSizeHint(w.sizeHint())

    def _sync_check_from_widget(self, item: QListWidgetItem, checked: bool):
        """Sync item check state from the embedded QCheckBox."""
        # Temporarily re-enable checkable to set the state
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)

    def _hide_per_spins(self):
        """Remove per-mutation QSpinBox widgets and restore built-in checkboxes."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            widget = self._list.itemWidget(item)
            if widget is not None:
                lbl = widget.findChild(QLabel)
                if lbl:
                    item.setText(lbl.text())
                self._list.removeItemWidget(item)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

    def _filter_list(self, text: str):
        text_lower = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            # Check both the item text and the label inside the widget
            visible_text = item.text()
            widget = self._list.itemWidget(item)
            if widget is not None:
                lbl = widget.findChild(QLabel)
                if lbl:
                    visible_text = lbl.text()
            item.setHidden(text_lower not in visible_text.lower())

    def _set_all(self, checked: bool):
        self._suppress = True
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._list.count()):
            item = self._list.item(i)
            # If in individual mode, sync via embedded checkbox
            widget = self._list.itemWidget(item)
            if widget is not None:
                chk = widget.findChild(QCheckBox)
                if chk is not None:
                    chk.setChecked(checked)
            else:
                item.setCheckState(state)
        self._suppress = False
        self._update_toggle_text()
        self._on_changed()

    def _on_item_changed(self, _item=None):
        if self._suppress:
            return
        self._update_toggle_text()
        self._on_changed()

    def _on_changed(self, _=None):
        if self._suppress:
            return
        self._parent_view._on_config_changed()

    def _count_checked(self) -> int:
        return sum(
            1 for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
        )

    def _update_toggle_text(self):
        n = self._count_checked()
        arrow = "\u25B2" if self._toggle.isChecked() else "\u25BC"
        self._toggle.setText(f"{self._title} ({n} selected) {arrow}")


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class ManualScoringView(QWidget):
    """Configurable point-based cat scoring and triage view."""

    _UI_STATE_KEY = "manual_scoring_state"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget { background:#0a0a18; }"
            "QLabel { color:#bbb; }"
            "QLineEdit { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 8px; }"
            "QSpinBox { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:2px 6px; min-width:55px; }"
            "QComboBox { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 8px; }"
            "QComboBox QAbstractItemView { background:#101023; color:#ddd; }"
            "QTableWidget { background:#101023; color:#ddd; border:1px solid #26264a; }"
            "QHeaderView::section { background:#151532; color:#7d8bb0; border:none;"
            " padding:4px; font-weight:bold; }"
            "QCheckBox { color:#bbb; spacing:6px; }"
            "QListWidget { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 10px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
            "QScrollArea { background:transparent; border:none; }"
            "QToolButton { color:#8899cc; border:none; text-align:left; padding:2px 0; }"
        )

        self._cats: list[Cat] = []
        self._alive: list[Cat] = []
        self._config: dict = dict(_DEFAULT_CONFIG)
        self._session_state: dict = _load_ui_state(self._UI_STATE_KEY)
        self._suppress_recompute = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self._splitter, 1)

        # --- Left panel: config ---
        self._config_panel = self._build_config_panel()
        self._splitter.addWidget(self._config_panel)

        # --- Right panel: table ---
        self._table_panel = self._build_table_panel()
        self._splitter.addWidget(self._table_panel)

        self._splitter.setSizes([380, 800])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        self._restore_session_state()

    # ---- Config panel construction ----------------------------------------

    def _build_config_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(460)

        container = QWidget()
        vb = QVBoxLayout(container)
        vb.setContentsMargins(12, 12, 12, 12)
        vb.setSpacing(10)

        title = QLabel("Manual Scoring")
        title.setStyleSheet("color:#f0f0ff; font-size:16px; font-weight:bold;")
        vb.addWidget(title)

        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet("color:#667; font-size:11px;")
        vb.addWidget(self._subtitle)

        # --- Stats ---
        vb.addWidget(self._section_label("Stats"))
        row, self._spin_stat = self._weight_row("Per stat point", 1)
        vb.addLayout(row)

        # --- Desired mutations ---
        vb.addWidget(self._section_label("Mutations"))
        self._desired_selector = _MutationSelector("Desired Mutations", 1, self)
        vb.addWidget(self._desired_selector)

        # --- Undesired mutations ---
        self._undesired_selector = _MutationSelector("Undesirable Mutations", -5, self)
        vb.addWidget(self._undesired_selector)

        # --- Inbredness ---
        vb.addWidget(self._section_label("Inbredness"))
        self._spin_inbredness: dict[str, QSpinBox] = {}
        for tier, default in [("not", 2), ("slightly", 0), ("moderately", -1), ("highly", -10), ("extremely", -10)]:
            row, spin = self._weight_row(tier.capitalize(), default)
            self._spin_inbredness[tier] = spin
            vb.addLayout(row)

        # --- Libido ---
        vb.addWidget(self._section_label("Libido"))
        self._spin_libido: dict[str, QSpinBox] = {}
        for tier, default in [("high", 1), ("average", 0), ("low", -10)]:
            row, spin = self._weight_row(tier.capitalize(), default)
            self._spin_libido[tier] = spin
            vb.addLayout(row)

        # --- Aggression ---
        vb.addWidget(self._section_label("Aggression"))
        self._spin_aggression: dict[str, QSpinBox] = {}
        for tier, default in [("high", 1), ("average", 0), ("low", -1)]:
            row, spin = self._weight_row(tier.capitalize(), default)
            self._spin_aggression[tier] = spin
            vb.addLayout(row)

        # --- Passives ---
        vb.addWidget(self._section_label("Passives"))
        row, self._spin_passive = self._weight_row("Per passive ability", 1)
        vb.addLayout(row)

        # --- Extra spells ---
        vb.addWidget(self._section_label("Extra Spells"))
        row, self._spin_spell = self._weight_row("Per extra spell", 0)
        vb.addLayout(row)

        # --- Sexuality ---
        vb.addWidget(self._section_label("Sexuality"))
        self._spin_sexuality: dict[str, QSpinBox] = {}
        for tier, default in [("straight", 0), ("bi", -10), ("gay", -10)]:
            row, spin = self._weight_row(tier.capitalize(), default)
            self._spin_sexuality[tier] = spin
            vb.addLayout(row)

        # --- Reset ---
        vb.addSpacing(12)
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        vb.addWidget(reset_btn)

        vb.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # ---- Table panel construction -----------------------------------------

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        vb = QVBoxLayout(panel)
        vb.setContentsMargins(8, 8, 8, 8)
        vb.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("Room:"))
        self._room_combo = QComboBox()
        self._room_combo.setMinimumWidth(140)
        self._room_combo.currentIndexChanged.connect(self._recompute)
        toolbar.addWidget(self._room_combo)

        self._chk_in_house = QCheckBox("In House only")
        self._chk_in_house.setChecked(True)
        self._chk_in_house.toggled.connect(self._recompute)
        toolbar.addWidget(self._chk_in_house)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("Highlight below:"))
        self._spin_threshold = QSpinBox()
        self._spin_threshold.setRange(-999, 999)
        self._spin_threshold.setValue(12)
        self._spin_threshold.valueChanged.connect(self._apply_threshold_highlight)
        toolbar.addWidget(self._spin_threshold)

        vb.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(_NUM_COLS)
        self._table.setHorizontalHeaderLabels(_HEADER_LABELS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            self._table.styleSheet()
            + "QTableWidget { alternate-background-color:#0c0c20; }"
        )

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Interactive)
        hdr.setSectionResizeMode(_COL_ROOM, QHeaderView.Interactive)
        self._table.setColumnWidth(_COL_NAME, 160)
        self._table.setColumnWidth(_COL_ROOM, 80)
        self._table.setColumnWidth(_COL_TOTAL, 60)
        for i in range(_COL_FIRST_BREAKDOWN, _NUM_COLS):
            self._table.setColumnWidth(i, 65)

        vb.addWidget(self._table, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#667; font-size:11px;")
        vb.addWidget(self._status_label)

        return panel

    # ---- Helpers ----------------------------------------------------------

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#8899cc; font-size:12px; font-weight:bold; margin-top:6px;")
        return lbl

    def _weight_row(self, label: str, default: int) -> tuple[QHBoxLayout, QSpinBox]:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setMinimumWidth(120)
        row.addWidget(lbl)
        spin = QSpinBox()
        spin.setRange(-99, 99)
        spin.setValue(default)
        spin.valueChanged.connect(self._on_config_changed)
        row.addWidget(spin)
        row.addStretch()
        return row, spin

    # ---- Mutation catalog rebuild -----------------------------------------

    def _rebuild_mutation_catalogs(self):
        """Rebuild both mutation selectors from current cats."""
        all_mutations = sorted({m for c in self._alive for m in (c.mutations or [])})

        prev_desired = set(self._config.get("desired_mutations", []))
        prev_desired_weights = self._config.get("desired_mutation_weights", {})
        self._desired_selector.rebuild(all_mutations, prev_desired, prev_desired_weights)
        self._desired_selector.apply_per_weights()

        prev_undesired = set(self._config.get("undesired_mutations", []))
        prev_undesired_weights = self._config.get("undesired_mutation_weights", {})
        self._undesired_selector.rebuild(all_mutations, prev_undesired, prev_undesired_weights)
        self._undesired_selector.apply_per_weights()

    # ---- Config reading ---------------------------------------------------

    def _read_config(self) -> dict:
        """Read all widget values into a config dict."""
        return {
            "stat_weight": self._spin_stat.value(),
            "desired_mutations": self._desired_selector.get_checked(),
            "desired_mutation_weights": self._desired_selector.get_per_weights(),
            "desired_use_individual": self._desired_selector.use_individual(),
            "desired_default_weight": self._desired_selector.default_weight(),
            "undesired_mutations": self._undesired_selector.get_checked(),
            "undesired_mutation_weights": self._undesired_selector.get_per_weights(),
            "undesired_use_individual": self._undesired_selector.use_individual(),
            "undesired_default_weight": self._undesired_selector.default_weight(),
            "inbredness_weights": {k: s.value() for k, s in self._spin_inbredness.items()},
            "libido_weights": {k: s.value() for k, s in self._spin_libido.items()},
            "aggression_weights": {k: s.value() for k, s in self._spin_aggression.items()},
            "passive_weight": self._spin_passive.value(),
            "extra_spell_weight": self._spin_spell.value(),
            "sexuality_weights": {k: s.value() for k, s in self._spin_sexuality.items()},
        }

    def _on_config_changed(self, _value=None):
        if self._suppress_recompute:
            return
        self._config = self._read_config()
        self._recompute()

    # ---- Data reception ---------------------------------------------------

    def set_cats(self, cats: list[Cat]):
        self._cats = cats or []
        self._alive = [c for c in self._cats if c.status != "Gone"]
        self._subtitle.setText(f"{len(self._alive)} cats alive, {len(self._cats)} total")
        self._populate_room_filter()
        self._rebuild_mutation_catalogs()
        self._recompute()

    # ---- Room filter ------------------------------------------------------

    def _populate_room_filter(self):
        prev = self._room_combo.currentData()
        self._room_combo.blockSignals(True)
        self._room_combo.clear()
        self._room_combo.addItem("All Rooms", "")
        occupied = sorted(
            {c.room for c in self._alive if c.room},
            key=lambda r: list(ROOM_KEYS).index(r) if r in ROOM_KEYS else 99,
        )
        for rk in occupied:
            display = ROOM_DISPLAY.get(rk, rk)
            count = sum(1 for c in self._alive if c.room == rk)
            self._room_combo.addItem(f"{display}  ({count})", rk)
        if prev:
            idx = self._room_combo.findData(prev)
            if idx >= 0:
                self._room_combo.setCurrentIndex(idx)
        self._room_combo.blockSignals(False)

    # ---- Recompute and display --------------------------------------------

    def _recompute(self, _=None):
        room_filter = self._room_combo.currentData() or ""
        in_house_only = self._chk_in_house.isChecked()

        cats = self._alive if in_house_only else self._cats
        if room_filter:
            cats = [c for c in cats if c.room == room_filter]

        scored: list[tuple[Cat, int, dict[str, int]]] = []
        for cat in cats:
            total, breakdown = compute_cat_score(cat, self._config)
            scored.append((cat, total, breakdown))

        scored.sort(key=lambda x: x[1], reverse=True)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(scored))

        for row, (cat, total, breakdown) in enumerate(scored):
            name_item = QTableWidgetItem(cat.name)
            name_item.setData(Qt.UserRole, cat.db_key)
            self._table.setItem(row, _COL_NAME, name_item)

            room_display = ROOM_DISPLAY.get(cat.room, cat.room or "\u2014")
            self._table.setItem(row, _COL_ROOM, QTableWidgetItem(room_display))

            total_item = _NumericItem(str(total))
            total_item.setData(Qt.UserRole, total)
            total_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, _COL_TOTAL, total_item)

            for ci, key in enumerate(_BREAKDOWN_KEYS):
                val = breakdown.get(key, 0)
                item = _NumericItem(str(val))
                item.setData(Qt.UserRole, val)
                item.setTextAlignment(Qt.AlignCenter)
                if val > 0:
                    item.setForeground(QBrush(QColor(120, 200, 130)))
                elif val < 0:
                    item.setForeground(QBrush(QColor(220, 100, 100)))
                self._table.setItem(row, _COL_FIRST_BREAKDOWN + ci, item)

        self._table.setSortingEnabled(True)
        self._apply_threshold_highlight()
        self._status_label.setText(f"{len(scored)} cats displayed")

    def _apply_threshold_highlight(self, _=None):
        threshold = self._spin_threshold.value()
        red_bg = QBrush(QColor(80, 20, 20))
        clear_bg = QBrush()
        for row in range(self._table.rowCount()):
            total_item = self._table.item(row, _COL_TOTAL)
            if total_item is None:
                continue
            val = total_item.data(Qt.UserRole)
            bg = red_bg if isinstance(val, int) and val < threshold else clear_bg
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None:
                    item.setBackground(bg)

    # ---- Reset defaults ---------------------------------------------------

    def _reset_defaults(self):
        self._suppress_recompute = True
        self._spin_stat.setValue(_DEFAULT_CONFIG["stat_weight"])
        self._desired_selector.reset()
        self._undesired_selector.reset()
        for k, v in _DEFAULT_CONFIG["inbredness_weights"].items():
            self._spin_inbredness[k].setValue(v)
        for k, v in _DEFAULT_CONFIG["libido_weights"].items():
            self._spin_libido[k].setValue(v)
        for k, v in _DEFAULT_CONFIG["aggression_weights"].items():
            self._spin_aggression[k].setValue(v)
        self._spin_passive.setValue(_DEFAULT_CONFIG["passive_weight"])
        self._spin_spell.setValue(_DEFAULT_CONFIG["extra_spell_weight"])
        for k, v in _DEFAULT_CONFIG["sexuality_weights"].items():
            self._spin_sexuality[k].setValue(v)
        self._spin_threshold.setValue(12)
        self._suppress_recompute = False
        self._config = self._read_config()
        self._recompute()

    # ---- Session state persistence ----------------------------------------

    def save_session_state(self):
        state = self._read_config()
        state["threshold"] = self._spin_threshold.value()
        state["room_filter"] = self._room_combo.currentData() or ""
        state["in_house_only"] = self._chk_in_house.isChecked()
        state["splitter_sizes"] = self._splitter.sizes()
        hdr = self._table.horizontalHeader()
        state["sort_column"] = hdr.sortIndicatorSection()
        state["sort_order"] = hdr.sortIndicatorOrder().value
        _save_ui_state(self._UI_STATE_KEY, state)

    def _restore_session_state(self):
        s = self._session_state
        if not s:
            return

        self._suppress_recompute = True

        self._spin_stat.setValue(s.get("stat_weight", _DEFAULT_CONFIG["stat_weight"]))

        # Restore mutation selector state (items rebuilt later in set_cats)
        self._desired_selector.set_state(
            use_individual=s.get("desired_use_individual", False),
            default_weight=s.get("desired_default_weight", 1),
            per_weights=s.get("desired_mutation_weights", {}),
        )
        self._undesired_selector.set_state(
            use_individual=s.get("undesired_use_individual", False),
            default_weight=s.get("undesired_default_weight", -5),
            per_weights=s.get("undesired_mutation_weights", {}),
        )

        for k, spin in self._spin_inbredness.items():
            spin.setValue(s.get("inbredness_weights", _DEFAULT_CONFIG["inbredness_weights"]).get(k, 0))
        for k, spin in self._spin_libido.items():
            spin.setValue(s.get("libido_weights", _DEFAULT_CONFIG["libido_weights"]).get(k, 0))
        for k, spin in self._spin_aggression.items():
            spin.setValue(s.get("aggression_weights", _DEFAULT_CONFIG["aggression_weights"]).get(k, 0))

        self._spin_passive.setValue(s.get("passive_weight", _DEFAULT_CONFIG["passive_weight"]))
        self._spin_spell.setValue(s.get("extra_spell_weight", _DEFAULT_CONFIG["extra_spell_weight"]))

        for k, spin in self._spin_sexuality.items():
            spin.setValue(s.get("sexuality_weights", _DEFAULT_CONFIG["sexuality_weights"]).get(k, 0))

        self._spin_threshold.setValue(s.get("threshold", 12))
        self._chk_in_house.setChecked(s.get("in_house_only", True))

        sizes = s.get("splitter_sizes")
        if sizes and len(sizes) == 2:
            self._splitter.setSizes(sizes)

        self._suppress_recompute = False

        # Build initial config — mutation lists restored later in set_cats
        self._config = self._read_config()
        self._config["desired_mutations"] = s.get("desired_mutations", [])
        self._config["desired_mutation_weights"] = s.get("desired_mutation_weights", {})
        self._config["undesired_mutations"] = s.get("undesired_mutations", [])
        self._config["undesired_mutation_weights"] = s.get("undesired_mutation_weights", {})

    def _restore_sort_order(self):
        """Called after table is populated to restore sort column/order."""
        s = self._session_state
        col = s.get("sort_column", _COL_TOTAL)
        order = Qt.SortOrder(s.get("sort_order", int(Qt.DescendingOrder)))
        self._table.sortByColumn(col, order)


class _NumericItem(QTableWidgetItem):
    """Table item that sorts numerically by UserRole data."""

    def __lt__(self, other):
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole) if other else None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return super().__lt__(other)
