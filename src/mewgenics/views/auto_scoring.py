"""Automatic Scoring View — scope-aware individual cat scoring.

Three-panel splitter: left (config) | center (score table) | right (traits/details).
Follows existing view patterns (set_cats, save_session_state, _tr()).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QCheckBox, QComboBox, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QListWidget, QListWidgetItem, QDialog, QGridLayout,
    QDoubleSpinBox, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QColor

from save_parser import Cat, STAT_NAMES, risk_percent, can_breed

from mewgenics.utils.localization import _tr
from mewgenics.utils.trait_ratings import TraitRatings
from mewgenics.scoring.engine import (
    BREED_PRIORITY_WEIGHTS, WEIGHT_UI_ROWS, WEIGHT_TOOLTIPS, SCORE_COLUMNS,
    TRAIT_RATING_OPTIONS, ScoreResult, ability_base, is_basic_trait,
)
from mewgenics.scoring.helpers import (
    build_relationship_maps, compute_seven_sets,
    compute_all_scores, compute_heatmap_norms,
)
from mewgenics.scoring.filters import FilterState, cat_passes_filter, cat_passes_pre_score_filter
from mewgenics.scoring.cat_stats import get_cat_stats
from mewgenics.utils.config import _saved_auto_scoring_auto_calc

from mewgenics.utils.localization import ROOM_DISPLAY
from save_parser import ROOM_KEYS

_STAT_NAMES = list(STAT_NAMES)
_N_STATS = len(_STAT_NAMES)

# Column layout: Name | Loc | 7 stats | [sep] | N score sub-cols | [sep] | Score
_COL_NAME = 0
_COL_LOC = 1
_COL_STAT_START = 2
_COL_SCORE_START = _COL_STAT_START + _N_STATS
_N_SCORE_COLS = len(SCORE_COLUMNS)
_COL_TOTAL = _COL_SCORE_START + _N_SCORE_COLS
_TOTAL_COLS = _COL_TOTAL + 1


class _ScoringWorker(QThread):
    """Runs the heavy scoring computation off the main thread."""
    finished = Signal(object)  # emits a dict payload

    def __init__(self, alive, cats, scope_cats, scope_set,
                 use_current_stats, add_mutation_stats,
                 ma_ratings, weights, breeding_cache=None,
                 run_revision: int = 0):
        super().__init__()
        self._alive = alive
        self._cats = cats
        self._scope_cats = scope_cats
        self._scope_set = scope_set
        self._use_current_stats = use_current_stats
        self._add_mutation_stats = add_mutation_stats
        self._ma_ratings = ma_ratings
        self._weights = dict(weights)
        self._breeding_cache = breeding_cache
        self._run_revision = run_revision

    def run(self):
        if self.isInterruptionRequested():
            self.finished.emit({"status": "canceled", "run_revision": self._run_revision})
            return
        hated_by_map, _ = build_relationship_maps(self._cats)
        seven_sets, scope_7_sets = compute_seven_sets(
            self._alive, self._scope_set,
            use_current_stats=self._use_current_stats,
            add_mutation_stats=self._add_mutation_stats,
            stat_names=_STAT_NAMES,
            should_cancel=self.isInterruptionRequested,
        )
        if seven_sets is None:
            self.finished.emit({"status": "canceled", "run_revision": self._run_revision})
            return
        risk_lookup = self._breeding_cache.get_risk if self._breeding_cache is not None else None
        result = compute_all_scores(
            self._alive, self._scope_cats, self._scope_set,
            seven_sets, scope_7_sets, hated_by_map,
            self._ma_ratings, _STAT_NAMES, self._weights,
            gene_risk_lookup=risk_lookup,
            use_current_stats=self._use_current_stats,
            add_mutation_stats=self._add_mutation_stats,
            should_cancel=self.isInterruptionRequested,
        )
        if result is None:
            self.finished.emit({"status": "canceled", "run_revision": self._run_revision})
            return
        self.finished.emit({
            "status": "ok",
            "run_revision": self._run_revision,
            "result": result,
            "seven_sets": seven_sets,
            "scope_7_sets": scope_7_sets,
        })


class AutoScoringView(QWidget):
    """Automatic cat scoring view with scope, weights, heatmap, and filters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget { background:#0a0a18; }"
            "QLabel { color:#bbb; }"
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
            "QDoubleSpinBox, QSpinBox { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:2px 6px; min-width:55px; }"
        )

        self._cats: list = []
        self._alive: list = []
        self._trait_ratings: Optional[TraitRatings] = None
        self._suppress_recompute = False
        self._stale = False  # True when cats changed but _recompute() was deferred
        self._scoring_worker: _ScoringWorker | None = None
        self._breeding_cache = None
        self._results_stale = True
        self._config_revision = 0
        self._auto_calc = _saved_auto_scoring_auto_calc()

        # Scoring state
        self._weights: dict[str, float] = dict(BREED_PRIORITY_WEIGHTS)
        self._filter_state = FilterState()
        self._results: dict[int, ScoreResult] = {}
        self._cat_sub_counts: dict[int, int] = {}
        self._scope_set: set[int] = set()
        self._scope_cats: list = []

        # Options
        self._display_mode = "score"  # score, values, both
        self._heatmap_on = False
        self._heat_algo = "column"
        self._show_stats = True
        self._hide_kittens = False
        self._hide_out_of_scope = False
        self._use_current_stats = False
        self._add_mutation_stats = False

        # Debounce save timer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._do_save)

        # Build UI
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self._splitter, 1)

        self._splitter.addWidget(self._build_left_panel())
        self._splitter.addWidget(self._build_center_panel())
        self._splitter.addWidget(self._build_right_panel())

        self._splitter.setSizes([300, 700, 280])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

    # ── Public API ────────────────────────────────────────────────────────

    def set_cats(self, cats: list):
        self._cats = cats or []
        self._alive = [c for c in self._cats if c.status != "Gone"]
        self._rebuild_scope_checkboxes()
        self._mark_dirty(clear_results=True, cancel_running=True)

    def set_trait_ratings(self, tr: TraitRatings):
        self._trait_ratings = tr
        self._load_from_trait_ratings()

    def set_cache(self, cache):
        self._breeding_cache = cache
        if self._scoring_worker is None:
            return
        self._mark_dirty(cancel_running=True)

    def save_session_state(self):
        self._do_save()

    def set_auto_recalculate(self, enabled: bool):
        self._auto_calc = bool(enabled)
        self._auto_calc_chk.blockSignals(True)
        self._auto_calc_chk.setChecked(self._auto_calc)
        self._auto_calc_chk.blockSignals(False)

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale and self._status_label.text() == "":
            self._status_label.setText(self._dirty_status_text())

    # ── Left panel ────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(380)

        container = QWidget()
        vb = QVBoxLayout(container)
        vb.setContentsMargins(10, 10, 10, 10)
        vb.setSpacing(6)

        # ── Profile ──
        vb.addWidget(self._section_label("PROFILE"))
        prof_row = QHBoxLayout()
        prof_row.setSpacing(6)
        self._profile_combo = QComboBox()
        self._profile_combo.setToolTip("Switch between 5 independent weight/trait profiles.\nEach profile saves its own weights, scope, and trait ratings.")
        for i in range(1, 6):
            self._profile_combo.addItem(f"Profile {i}", i)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        prof_row.addWidget(self._profile_combo, 1)
        vb.addLayout(prof_row)

        # ── Display ──
        vb.addWidget(self._section_label("DISPLAY"))
        disp_row = QHBoxLayout()
        disp_row.setSpacing(6)
        disp_row.addWidget(QLabel("Mode:"))
        self._display_combo = QComboBox()
        self._display_combo.setToolTip("Score: show sub-scores per category.\nValues: show raw values (risk %, stat sum, etc.).\nBoth: show both in each cell.")
        self._display_combo.addItems(["Score", "Values", "Both"])
        self._display_combo.currentIndexChanged.connect(self._on_display_changed)
        disp_row.addWidget(self._display_combo, 1)
        vb.addLayout(disp_row)

        heat_row = QHBoxLayout()
        heat_row.setSpacing(6)
        self._chk_heatmap = QCheckBox("Heatmap")
        self._chk_heatmap.setToolTip("Color-code score cells from red (negative) through green (positive).\nMakes it easy to spot strengths and weaknesses at a glance.")
        self._chk_heatmap.stateChanged.connect(self._on_heatmap_toggled)
        heat_row.addWidget(self._chk_heatmap)
        self._heat_algo_combo = QComboBox()
        self._heat_algo_combo.setToolTip("Column: colors are relative to the best/worst in each column.\nRow: colors are relative to the best/worst across each cat's own scores.")
        self._heat_algo_combo.addItems(["Column", "Row"])
        self._heat_algo_combo.currentIndexChanged.connect(self._on_heat_algo_changed)
        heat_row.addWidget(self._heat_algo_combo)
        heat_row.addStretch()
        vb.addLayout(heat_row)

        self._chk_show_stats = QCheckBox("Show stat columns")
        self._chk_show_stats.setToolTip("Show or hide the 7 base stat columns (STR, DEX, etc.) in the table.")
        self._chk_show_stats.setChecked(True)
        self._chk_show_stats.stateChanged.connect(self._on_show_stats_toggled)
        vb.addWidget(self._chk_show_stats)

        self._btn_stats_overview = QPushButton("Current Stats...")
        self._btn_stats_overview.setToolTip("Open a popup showing stat distribution across all cats.\nUseful for understanding how rare each stat value is.")
        self._btn_stats_overview.clicked.connect(self._open_stats_overview)
        vb.addWidget(self._btn_stats_overview)

        # ── Scope ──
        vb.addWidget(self._section_label("SCOPE"))
        self._chk_all_cats = QCheckBox("All Cats")
        self._chk_all_cats.setToolTip("Include all alive cats in the scoring scope.\nUncheck to select specific rooms instead.")
        self._chk_all_cats.setChecked(True)
        self._chk_all_cats.stateChanged.connect(self._on_scope_changed)
        vb.addWidget(self._chk_all_cats)
        self._scope_container = QVBoxLayout()
        self._scope_container.setSpacing(2)
        vb.addLayout(self._scope_container)
        self._room_checkboxes: dict[str, QCheckBox] = {}

        # ── Options ──
        vb.addWidget(self._section_label("OPTIONS"))
        self._chk_hide_kittens = QCheckBox("Hide kittens")
        self._chk_hide_kittens.setToolTip("Hide cats younger than 1 year from the table.\nKittens can't breed yet, so they add noise to the list.")
        self._chk_hide_kittens.stateChanged.connect(self._on_option_changed)
        vb.addWidget(self._chk_hide_kittens)
        self._chk_hide_oos = QCheckBox("Hide out-of-scope")
        self._chk_hide_oos.setToolTip("Hide cats that aren't in any selected scope room.\nUseful for focusing only on cats you're actively breeding.")
        self._chk_hide_oos.stateChanged.connect(self._on_option_changed)
        vb.addWidget(self._chk_hide_oos)
        self._chk_use_current = QCheckBox("Use current stats")
        self._chk_use_current.setToolTip("Score using current total stats (including room/furniture buffs)\ninstead of base stats. Useful for seeing effective breeding power.")
        self._chk_use_current.stateChanged.connect(self._on_option_changed)
        vb.addWidget(self._chk_use_current)
        self._chk_add_mutation = QCheckBox("Add mutation stats")
        self._chk_add_mutation.setToolTip("Include stat bonuses from visual mutations (e.g. Conjoined Body +2 CON)\non top of the stat values used for scoring.")
        self._chk_add_mutation.stateChanged.connect(self._on_option_changed)
        vb.addWidget(self._chk_add_mutation)

        # ── Weights ──
        vb.addWidget(self._section_label("WEIGHTS"))
        self._weight_spins: dict[str, QDoubleSpinBox] = {}
        for key, label_spec in WEIGHT_UI_ROWS:
            if key is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color:#2a2a4a;")
                sep.setFixedHeight(1)
                vb.addWidget(sep)
                continue
            row = QHBoxLayout()
            row.setSpacing(4)
            if isinstance(label_spec, tuple):
                if label_spec[0]:
                    row.addWidget(QLabel(label_spec[0]))
                row.addWidget(QLabel(label_spec[1]))
            else:
                row.addWidget(QLabel(label_spec))
            row.addStretch()
            spin = QDoubleSpinBox()
            spin.setRange(-100.0, 100.0)
            spin.setSingleStep(0.5)
            spin.setDecimals(1)
            spin.setValue(self._weights.get(key, 0.0))
            spin.setFixedWidth(70)
            tip = WEIGHT_TOOLTIPS.get(key)
            if tip:
                spin.setToolTip(tip)
            spin.valueChanged.connect(self._on_weight_changed)
            self._weight_spins[key] = spin
            row.addWidget(spin)
            vb.addLayout(row)

        # ── Filters ──
        vb.addWidget(self._section_label("FILTERS"))
        self._btn_filters = QPushButton("Edit Filters...")
        self._btn_filters.setToolTip("Open the filter dialog to hide cats by tier, gender, room,\nscore range, or other criteria. Active filters are shown below.")
        self._btn_filters.clicked.connect(self._open_filter_dialog)
        vb.addWidget(self._btn_filters)
        self._filter_summary = QLabel("No active filters")
        self._filter_summary.setStyleSheet("color:#666; font-size:10px;")
        vb.addWidget(self._filter_summary)

        vb.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Center panel (score table) ────────────────────────────────────────

    def _build_center_panel(self) -> QWidget:
        w = QWidget()
        vb = QVBoxLayout(w)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 0)
        toolbar.setSpacing(6)
        self._calculate_btn = QPushButton("Calculate")
        self._calculate_btn.setToolTip("Run the scoring computation for all cats.\nRequired after changing weights, scope, or options.")
        self._calculate_btn.clicked.connect(self._recompute)
        toolbar.addWidget(self._calculate_btn)
        self._stop_btn = QPushButton("Stop Calc")
        self._stop_btn.setToolTip("Cancel the running scoring computation.")
        self._stop_btn.clicked.connect(self._stop_scoring)
        self._stop_btn.setEnabled(False)
        toolbar.addWidget(self._stop_btn)
        self._auto_calc_chk = QCheckBox("Auto Calc")
        self._auto_calc_chk.setToolTip("Automatically recalculate scores when weights, scope, or options change.")
        self._auto_calc_chk.setChecked(self._auto_calc)
        self._auto_calc_chk.toggled.connect(self._on_auto_calc_toggled)
        toolbar.addWidget(self._auto_calc_chk)
        toolbar.addStretch()
        vb.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(_TOTAL_COLS)

        headers = ["Name", "Room"]
        headers += _STAT_NAMES
        headers += [col_name for col_name, _ in SCORE_COLUMNS]
        headers += ["Score"]
        self._table.setHorizontalHeaderLabels(headers)

        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(False)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        hh.setSectionResizeMode(_COL_LOC, QHeaderView.Fixed)
        self._table.setColumnWidth(_COL_LOC, 80)
        for i in range(_COL_STAT_START, _COL_STAT_START + _N_STATS):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self._table.setColumnWidth(i, 36)
        for i in range(_COL_SCORE_START, _COL_SCORE_START + _N_SCORE_COLS):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self._table.setColumnWidth(i, 42)
        hh.setSectionResizeMode(_COL_TOTAL, QHeaderView.Fixed)
        self._table.setColumnWidth(_COL_TOTAL, 56)

        # Header tooltips for score columns
        _col_tips = {
            "Sum":    "Stat sum percentile bonus",
            "Age":    "Age penalty (over threshold)",
            "7rare":  "Rarity bonus per stat at 7",
            "7cnt":   "Bonus for multiple stats at 7",
            "7sub":   "Penalty if 7-set is dominated by another cat",
            "CHA":    "CHA penalty (CHA 4 = 1x, CHA \u2264 3 = 2x)",
            "Sex":    "Sexuality preference (gay/bi)",
            "Lib":    "Libido bonus/penalty (high/low)",
            "Gender": "Unknown gender (?) bonus",
            "Gene":   "Genetic safety risk/bonus",
            "Aggro":  "Aggression bonus/penalty (low/high)",
            "\U0001f4a5\U0001f52d":  "Hate relationships in scope",
            "\U0001f4a5\U0001f3e0":  "Hate relationships in same room",
            "\U0001f497\U0001f52d":  "Love relationships in scope",
            "\U0001f497\U0001f3e0":  "Love relationships in same room",
            "Trait":  "Trait rating score (top priority/desirable/undesirable)",
            "Score":  "Total breed priority score (sum of all sub-scores)",
        }
        for ci, (col_name, _) in enumerate(SCORE_COLUMNS):
            header_item = self._table.horizontalHeaderItem(_COL_SCORE_START + ci)
            if header_item and col_name in _col_tips:
                header_item.setToolTip(_col_tips[col_name])
        total_header = self._table.horizontalHeaderItem(_COL_TOTAL)
        if total_header:
            total_header.setToolTip(_col_tips["Score"])

        self._table.currentCellChanged.connect(self._on_row_selected)
        vb.addWidget(self._table)

        # Status bar
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#666; font-size:10px; padding:2px 8px;")
        vb.addWidget(self._status_label)

        return w

    # ── Right panel (traits + details) ────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(320)

        container = QWidget()
        vb = QVBoxLayout(container)
        vb.setContentsMargins(8, 8, 8, 8)
        vb.setSpacing(6)

        # Trait tabs
        vb.addWidget(self._section_label("TRAIT RATINGS"))
        self._trait_tabs = QTabWidget()
        self._trait_tabs.setStyleSheet(
            "QTabWidget::pane { border:1px solid #2a2a4a; }"
            "QTabBar::tab { background:#151532; color:#888; padding:4px 12px;"
            " border:1px solid #2a2a4a; border-bottom:none; }"
            "QTabBar::tab:selected { background:#1a1a32; color:#ccc; }"
        )

        self._ability_list = QListWidget()
        self._ability_list.setToolTip("Double-click a trait to cycle its rating:\nTop Priority > Desirable > Neutral > Undecided > Undesirable")
        self._mutation_list = QListWidget()
        self._mutation_list.setToolTip("Double-click a mutation to cycle its rating.\nRatings are shared with the Manual Scoring view via profiles.")
        self._trait_tabs.addTab(self._ability_list, "Abilities")
        self._trait_tabs.addTab(self._mutation_list, "Mutations")
        self._ability_list.itemDoubleClicked.connect(self._on_trait_double_clicked)
        self._mutation_list.itemDoubleClicked.connect(self._on_trait_double_clicked)
        vb.addWidget(self._trait_tabs, 1)

        # Score breakdown
        vb.addWidget(self._section_label("SCORE BREAKDOWN"))
        self._breakdown_list = QListWidget()
        self._breakdown_list.setToolTip("Detailed score breakdown for the selected cat.\nShows which weights contributed how many points.")
        self._breakdown_list.setMaximumHeight(200)
        vb.addWidget(self._breakdown_list)

        # Children
        vb.addWidget(self._section_label("CHILDREN IN SCOPE"))
        self._children_list = QListWidget()
        self._children_list.setToolTip("Children of the selected cat that are in the current scope.\nUseful for tracking lineage coverage.")
        self._children_list.setMaximumHeight(120)
        vb.addWidget(self._children_list)

        # Top risks
        vb.addWidget(self._section_label("TOP BREEDING RISKS"))
        self._risk_list = QListWidget()
        self._risk_list.setToolTip("Highest genetic risk pairings for the selected cat.\nShows the worst-case partners by inbreeding risk %.")
        self._risk_list.setMaximumHeight(120)
        vb.addWidget(self._risk_list)

        vb.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#5566aa; font-size:10px; font-weight:bold;"
            " padding:6px 0 2px 0; letter-spacing:1px;"
        )
        return lbl

    # ── Scope management ──────────────────────────────────────────────────

    def _rebuild_scope_checkboxes(self):
        # Clear existing
        for cb in self._room_checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self._room_checkboxes.clear()

        rooms = sorted({c.room for c in self._alive if c.room})
        for rk in rooms:
            display = ROOM_DISPLAY.get(rk, rk)
            room_cats = [c for c in self._alive if c.room == rk]
            # Show filtered counts when filters are active
            filtered = [
                c for c in room_cats
                if cat_passes_pre_score_filter(
                    c, self._filter_state,
                    use_current_stats=self._use_current_stats,
                    add_mutation_stats=self._add_mutation_stats,
                )
            ]
            n_m = sum(1 for c in filtered if c.gender_display == "M")
            n_f = sum(1 for c in filtered if c.gender_display == "F")
            n_q = sum(1 for c in filtered if c.gender_display == "?")
            total = len(filtered)
            total_room = len(room_cats)
            label = f"{display}  ({n_m}M {n_f}F"
            if n_q:
                label += f" {n_q}?"
            if total < total_room:
                label += f" | {total}/{total_room}"
            label += ")"
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setProperty("room_key", rk)
            cb.stateChanged.connect(self._on_scope_changed)
            self._room_checkboxes[rk] = cb
            self._scope_container.addWidget(cb)

    def _compute_scope(self):
        """Determine which cats are in scope based on checkboxes and filters."""
        if self._chk_all_cats.isChecked():
            candidates = self._alive
        else:
            active_rooms = {rk for rk, cb in self._room_checkboxes.items() if cb.isChecked()}
            candidates = [c for c in self._alive if c.room in active_rooms]
        # Apply pre-score filters to exclude cats from scope
        self._scope_cats = [
            c for c in candidates
            if cat_passes_pre_score_filter(
                c, self._filter_state,
                use_current_stats=self._use_current_stats,
                add_mutation_stats=self._add_mutation_stats,
            )
        ]
        self._scope_set = {id(c) for c in self._scope_cats}

    def _dirty_status_text(self) -> str:
        if not self._alive:
            return "No cats loaded"
        scope_info = f"  ({len(self._scope_cats)} in scope / {len(self._alive)} alive)"
        if self._scoring_worker is not None:
            return "Calculation running..." + scope_info
        if self._results and not self._results_stale:
            return "Showing previous scores." + scope_info
        if self._auto_calc:
            return "Scores are out of date. Recalculating..." + scope_info
        return "Scores are out of date. Click Calculate to recompute." + scope_info

    def _clear_results(self):
        self._results = {}
        self._cat_sub_counts = {}
        self._table.setRowCount(0)
        self._breakdown_list.clear()
        self._children_list.clear()
        self._risk_list.clear()

    def _update_calc_buttons(self):
        running = self._scoring_worker is not None
        self._calculate_btn.setEnabled(bool(self._alive) and not running)
        self._stop_btn.setEnabled(running)

    def _on_auto_calc_toggled(self, checked: bool):
        from mewgenics.utils.config import _set_auto_scoring_auto_calc
        self._auto_calc = bool(checked)
        _set_auto_scoring_auto_calc(self._auto_calc)
        if self._auto_calc and self._results_stale and self._alive:
            self._recompute()

    def _mark_dirty(self, *, clear_results: bool = False, cancel_running: bool = False):
        if cancel_running and self._scoring_worker is not None:
            self._stop_scoring(update_status=False)
        self._config_revision += 1
        self._results_stale = True
        self._stale = True
        if clear_results:
            self._clear_results()
        self._compute_scope()
        self._update_trait_lists()
        self._status_label.setText(self._dirty_status_text())
        self._update_calc_buttons()
        self._schedule_save()
        if self._auto_calc and self._alive:
            self._recompute()

    # ── Recompute flow ────────────────────────────────────────────────────

    def _recompute(self):
        if self._suppress_recompute:
            return
        self._stale = False
        if not self._alive:
            self._table.setRowCount(0)
            self._status_label.setText("No cats loaded")
            return

        # Retire the previous worker if still running — request cancellation
        # and let it clean up via deleteLater when its thread finishes.
        old = self._scoring_worker
        if old is not None:
            old.requestInterruption()
            old.finished.disconnect(self._on_scoring_done)
            old.finished.connect(old.deleteLater)
            self._scoring_worker = None

        self._read_options()
        self._compute_scope()

        # Gather ratings
        ma_ratings = {}
        if self._trait_ratings:
            ma_ratings = dict(self._trait_ratings.ratings)

        self._status_label.setText("Computing scores...")
        self._stale = False
        self._update_calc_buttons()

        worker = _ScoringWorker(
            self._alive, self._cats, self._scope_cats, self._scope_set,
            self._use_current_stats, self._add_mutation_stats,
            ma_ratings, self._weights,
            breeding_cache=self._breeding_cache,
            run_revision=self._config_revision,
        )
        worker.finished.connect(self._on_scoring_done)
        self._scoring_worker = worker
        self._update_calc_buttons()
        worker.start()

    def _stop_scoring(self, update_status: bool = True):
        worker = self._scoring_worker
        if worker is None:
            return
        worker.requestInterruption()
        if update_status:
            self._status_label.setText("Stopping calculation...")
        self._update_calc_buttons()

    def _on_scoring_done(self, payload):
        """Handle completed scoring from the background worker."""
        worker = self.sender()
        if worker is self._scoring_worker:
            self._scoring_worker = None
        if worker is not None:
            worker.deleteLater()
        self._update_calc_buttons()

        if not isinstance(payload, dict):
            self._status_label.setText(self._dirty_status_text())
            return
        if payload.get("status") != "ok":
            self._status_label.setText(self._dirty_status_text())
            return
        if payload.get("run_revision") != self._config_revision:
            self._status_label.setText(self._dirty_status_text())
            return

        results_tuple = payload["result"]

        (self._results, self._cat_sub_counts, all_scores_sorted,
         all_scope_gene_risks, all_scope_children, max_7_count,
         scope_stat_sums, pair_risk_cache) = results_tuple
        self._results_stale = False
        self._stale = False

        # Heatmap norms
        col_max_abs, row_max_abs, score_max_abs = compute_heatmap_norms(
            self._results, self._alive, self._heatmap_on, self._heat_algo,
        )

        # Apply filters and populate
        self._populate_table(col_max_abs, row_max_abs, score_max_abs)
        self._update_trait_lists()
        self._schedule_save()

    def _read_options(self):
        self._hide_kittens = self._chk_hide_kittens.isChecked()
        self._hide_out_of_scope = self._chk_hide_oos.isChecked()
        self._use_current_stats = self._chk_use_current.isChecked()
        self._add_mutation_stats = self._chk_add_mutation.isChecked()
        self._heatmap_on = self._chk_heatmap.isChecked()
        self._heat_algo = self._heat_algo_combo.currentText().lower()

        # Read weights from spins
        for key, spin in self._weight_spins.items():
            self._weights[key] = spin.value()

    # ── Table population ──────────────────────────────────────────────────

    def _populate_table(self, col_max_abs, row_max_abs, score_max_abs):
        # Filter cats
        visible = []
        for cat in self._alive:
            if self._hide_kittens and getattr(cat, 'age', 99) < 1:
                continue
            if self._hide_out_of_scope and id(cat) not in self._scope_set:
                continue
            result = self._results.get(id(cat))
            if result and not cat_passes_filter(
                cat,
                self._filter_state,
                result,
                self._scope_set,
                use_current_stats=self._use_current_stats,
                add_mutation_stats=self._add_mutation_stats,
            ):
                continue
            visible.append(cat)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(visible))

        show_stats = self._chk_show_stats.isChecked()
        show_scores = self._display_mode in ("score", "both")
        show_values = self._display_mode in ("values", "both")

        for row, cat in enumerate(visible):
            result = self._results.get(id(cat))
            stats = get_cat_stats(cat, self._use_current_stats, self._add_mutation_stats)

            # Name
            name_item = QTableWidgetItem(cat.name)
            name_item.setData(Qt.UserRole, id(cat))
            self._table.setItem(row, _COL_NAME, name_item)

            # Room
            room_display = ROOM_DISPLAY.get(cat.room, cat.room or '\u2014')
            room_item = QTableWidgetItem(room_display)
            room_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, _COL_LOC, room_item)

            # Stat columns
            for si, sn in enumerate(_STAT_NAMES):
                col = _COL_STAT_START + si
                val = stats.get(sn, 0)
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, val)
                item.setTextAlignment(Qt.AlignCenter)
                if val >= 7:
                    item.setForeground(QColor("#1ec8a0"))
                elif val == 6:
                    item.setForeground(QColor("#999"))
                elif val < 5:
                    item.setForeground(QColor("#555"))
                self._table.setItem(row, col, item)
                if not show_stats:
                    self._table.setColumnHidden(col, True)
                else:
                    self._table.setColumnHidden(col, False)

            # Score sub-columns
            if result:
                for sci, (col_name, keys) in enumerate(SCORE_COLUMNS):
                    col = _COL_SCORE_START + sci
                    sub_val = sum(result.subtotals.get(k, 0.0) for k in keys)
                    item = QTableWidgetItem()

                    if show_values:
                        item.setText(f"{sub_val:+.1f}" if sub_val != 0 else "")
                    elif show_scores:
                        item.setData(Qt.DisplayRole, round(sub_val, 1) if sub_val != 0 else "")

                    item.setTextAlignment(Qt.AlignCenter)
                    item.setData(Qt.UserRole, sub_val)

                    # Heatmap coloring
                    if self._heatmap_on and sub_val != 0:
                        if self._heat_algo == "row" and id(cat) in row_max_abs:
                            norm = sub_val / row_max_abs[id(cat)]
                        elif sci in col_max_abs:
                            norm = sub_val / col_max_abs[sci]
                        else:
                            norm = 0
                        norm = max(-1.0, min(1.0, norm))
                        if norm > 0:
                            intensity = int(norm * 60)
                            item.setBackground(QColor(20, 80 + intensity, 40 + intensity, 80 + intensity))
                        elif norm < 0:
                            intensity = int(abs(norm) * 60)
                            item.setBackground(QColor(80 + intensity, 20, 20, 80 + intensity))

                    self._table.setItem(row, col, item)

                # Total score
                total_item = QTableWidgetItem()
                total_item.setData(Qt.DisplayRole, round(result.total, 1))
                total_item.setTextAlignment(Qt.AlignCenter)
                total_item.setForeground(QColor(result.tier_color))

                if self._heatmap_on and score_max_abs > 0:
                    norm = result.total / score_max_abs
                    norm = max(-1.0, min(1.0, norm))
                    if norm > 0:
                        intensity = int(norm * 60)
                        total_item.setBackground(QColor(20, 80 + intensity, 40 + intensity, 80 + intensity))
                    elif norm < 0:
                        intensity = int(abs(norm) * 60)
                        total_item.setBackground(QColor(80 + intensity, 20, 20, 80 + intensity))

                self._table.setItem(row, _COL_TOTAL, total_item)

        self._table.setSortingEnabled(True)
        n_scope = len(self._scope_cats)
        self._status_label.setText(
            f"{len(visible)} visible  \u00b7  {n_scope} in scope  \u00b7  {len(self._alive)} alive"
        )

    def _refresh_table_from_results(self):
        if not self._results or self._results_stale:
            self._status_label.setText(self._dirty_status_text())
            return
        col_max_abs, row_max_abs, score_max_abs = compute_heatmap_norms(
            self._results, self._alive, self._heatmap_on, self._heat_algo,
        )
        self._populate_table(col_max_abs, row_max_abs, score_max_abs)

    # ── Right panel updates ───────────────────────────────────────────────

    def _update_trait_lists(self):
        """Rebuild trait rating lists from all cats in scope."""
        abilities: dict[str, int | None] = {}
        mutations: dict[str, int | None] = {}

        for cat in self._scope_cats:
            for a in list(cat.abilities) + list(cat.passive_abilities) + list(getattr(cat, 'disorders', [])):
                base = ability_base(a)
                if not is_basic_trait(base) and base not in abilities:
                    abilities[base] = self._trait_ratings.get_rating(base) if self._trait_ratings else None
            for m in list(cat.mutations) + list(getattr(cat, 'defects', [])):
                if not is_basic_trait(m) and m not in mutations:
                    mutations[m] = self._trait_ratings.get_rating(m) if self._trait_ratings else None

        self._ability_list.clear()
        for name in sorted(abilities):
            self._add_trait_item(self._ability_list, name, abilities[name])

        self._mutation_list.clear()
        for name in sorted(mutations):
            self._add_trait_item(self._mutation_list, name, mutations[name])

    def _add_trait_item(self, list_widget: QListWidget, name: str, rating: int | None):
        item = QListWidgetItem()
        rating_label = "Undecided"
        for label, val in TRAIT_RATING_OPTIONS:
            if val == rating:
                rating_label = label
                break
        item.setText(f"{name}  [{rating_label}]")
        item.setData(Qt.UserRole, name)
        if rating == 2:
            item.setForeground(QColor("#f0c060"))
        elif rating == 1:
            item.setForeground(QColor("#1ec8a0"))
        elif rating == -1:
            item.setForeground(QColor("#e04040"))
        else:
            item.setForeground(QColor("#888"))
        list_widget.addItem(item)

    def _on_trait_double_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if not name or not self._trait_ratings:
            return
        current = self._trait_ratings.get_rating(name)
        # Cycle: None -> 1 -> 2 -> -1 -> 0 -> None
        cycle = [None, 1, 2, -1, 0]
        idx = cycle.index(current) if current in cycle else 0
        new_val = cycle[(idx + 1) % len(cycle)]
        self._trait_ratings.set_rating(name, new_val)
        self._update_trait_lists()
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _on_row_selected(self, row, col, prev_row, prev_col):
        if row < 0:
            return
        name_item = self._table.item(row, _COL_NAME)
        if not name_item:
            return
        cat_id = name_item.data(Qt.UserRole)
        cat = None
        for c in self._alive:
            if id(c) == cat_id:
                cat = c
                break
        if not cat:
            return

        # Update breakdown
        result = self._results.get(cat_id)
        self._breakdown_list.clear()
        if result:
            for label, pts in result.breakdown:
                item = QListWidgetItem(f"{pts:+.1f}  {label}")
                if pts > 0:
                    item.setForeground(QColor("#1ec8a0"))
                elif pts < 0:
                    item.setForeground(QColor("#e04040"))
                else:
                    item.setForeground(QColor("#888"))
                self._breakdown_list.addItem(item)
            total_item = QListWidgetItem(f"{'─' * 20}")
            total_item.setForeground(QColor("#555"))
            self._breakdown_list.addItem(total_item)
            summary = QListWidgetItem(f"{result.total:+.1f}  TOTAL  ({result.tier})")
            summary.setForeground(QColor(result.tier_color))
            self._breakdown_list.addItem(summary)

        # Children in scope
        self._children_list.clear()
        for ch in getattr(cat, 'children', []):
            if id(ch) in self._scope_set:
                self._children_list.addItem(ch.name)

        # Top risks
        self._risk_list.clear()
        risks = []
        for partner in self._scope_cats:
            if partner is cat:
                continue
            ok, _ = can_breed(cat, partner)
            if not ok:
                continue
            if self._breeding_cache is not None:
                r = self._breeding_cache.get_risk(cat, partner)
            else:
                r = risk_percent(cat, partner)
            if r > 0:
                risks.append((r, partner.name))
        risks.sort(reverse=True)
        for r, name in risks[:10]:
            item = QListWidgetItem(f"{r:.1f}%  {name}")
            if r > 10:
                item.setForeground(QColor("#e04040"))
            elif r > 5:
                item.setForeground(QColor("#e08030"))
            else:
                item.setForeground(QColor("#888"))
            self._risk_list.addItem(item)

    # ── Event handlers ────────────────────────────────────────────────────

    def _on_profile_changed(self):
        if self._suppress_recompute or not self._trait_ratings:
            return
        slot = self._profile_combo.currentData()
        if slot is None:
            return
        self._save_to_trait_ratings()
        self._trait_ratings.switch_profile(slot)
        self._trait_ratings.save()
        self._load_from_trait_ratings()
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _on_display_changed(self):
        mode = self._display_combo.currentText().lower()
        self._display_mode = mode
        self._refresh_table_from_results()
        self._schedule_save()

    def _on_heatmap_toggled(self):
        self._heatmap_on = self._chk_heatmap.isChecked()
        self._refresh_table_from_results()
        self._schedule_save()

    def _on_heat_algo_changed(self):
        self._heat_algo = self._heat_algo_combo.currentText().lower()
        if self._heatmap_on:
            self._refresh_table_from_results()
        self._schedule_save()

    def _on_show_stats_toggled(self):
        show = self._chk_show_stats.isChecked()
        for si in range(_N_STATS):
            self._table.setColumnHidden(_COL_STAT_START + si, not show)
        self._schedule_save()

    def _on_scope_changed(self):
        if self._suppress_recompute:
            return
        # If a room checkbox was unchecked, auto-uncheck "All Cats"
        sender = self.sender()
        if sender is not self._chk_all_cats and not sender.isChecked():
            self._chk_all_cats.blockSignals(True)
            self._chk_all_cats.setChecked(False)
            self._chk_all_cats.blockSignals(False)
        # If "All Cats" was checked, re-check all room checkboxes
        if sender is self._chk_all_cats and self._chk_all_cats.isChecked():
            for cb in self._room_checkboxes.values():
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _on_option_changed(self):
        if self._suppress_recompute:
            return
        sender = self.sender()
        if sender in (self._chk_hide_kittens, self._chk_hide_oos):
            self._read_options()
            self._refresh_table_from_results()
            self._schedule_save()
            return
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _on_weight_changed(self):
        if self._suppress_recompute:
            return
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _open_stats_overview(self):
        from mewgenics.dialogs import StatsOverviewDialog
        dlg = StatsOverviewDialog(self._cats, room_display=ROOM_DISPLAY, parent=self)
        dlg.show()

    def _open_filter_dialog(self):
        dlg = FilterDialog(self._filter_state, self._alive, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._filter_state = dlg.result_state()
            self._update_filter_summary()
            self._rebuild_scope_checkboxes()
            self._mark_dirty(cancel_running=True)
            self._schedule_save()

    def _update_filter_summary(self):
        active = []
        fs = self._filter_state
        if fs.age_active:
            active.append("Age")
        if fs.gender_active:
            active.append("Gender")
        if fs.score_active:
            active.append("Score")
        if fs.sum_active:
            active.append("Sum")
        if fs.count7_active:
            active.append("7-count")
        if fs.aggro_active:
            active.append("Aggro")
        if fs.libido_active:
            active.append("Libido")
        if fs.gene_active:
            active.append("Gene risk")
        if fs.children_active:
            active.append("Children")
        if fs.injury_active:
            active.append("Injuries")
        if fs.location_active:
            active.append("Location")
        any_stat = any(sf.get("active") for sf in fs.stat_filters.values())
        if any_stat:
            active.append("Stats")
        if active:
            self._filter_summary.setText(f"Active: {', '.join(active)}")
        else:
            self._filter_summary.setText("No active filters")

    # ── Persistence ───────────────────────────────────────────────────────

    def _save_to_trait_ratings(self):
        if not self._trait_ratings:
            return
        self._read_options()
        self._trait_ratings.set_auto_weights(self._weights)
        self._trait_ratings.set_auto_options({
            "hide_kittens": self._hide_kittens,
            "display_mode": self._display_mode,
            "heatmap_on": self._heatmap_on,
            "heat_algo": self._heat_algo,
            "show_stats": self._chk_show_stats.isChecked(),
            "use_current_stats": self._use_current_stats,
            "add_mutation_stats": self._add_mutation_stats,
            "hide_out_of_scope": self._hide_out_of_scope,
            "all_cats": self._chk_all_cats.isChecked(),
            "scope": {rk: cb.isChecked() for rk, cb in self._room_checkboxes.items()},
            "filters": self._filter_state.to_dict(),
            "sort_col": self._table.horizontalHeader().sortIndicatorSection(),
            "sort_desc": self._table.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder,
            "splitter_sizes": self._splitter.sizes(),
        })

    def _load_from_trait_ratings(self):
        if not self._trait_ratings:
            return
        self._suppress_recompute = True

        # Profile combo
        idx = self._profile_combo.findData(self._trait_ratings.active_profile)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)

        # Weights
        saved_weights = self._trait_ratings.get_auto_weights()
        if saved_weights:
            self._weights.update(saved_weights)
            for key, spin in self._weight_spins.items():
                if key in self._weights:
                    spin.setValue(self._weights[key])

        # Options
        opts = self._trait_ratings.get_auto_options()
        if opts:
            self._chk_hide_kittens.setChecked(opts.get("hide_kittens", False))
            mode = opts.get("display_mode", "score")
            idx = self._display_combo.findText(mode.capitalize())
            if idx >= 0:
                self._display_combo.setCurrentIndex(idx)
            self._chk_heatmap.setChecked(opts.get("heatmap_on", False))
            algo = opts.get("heat_algo", "column")
            idx = self._heat_algo_combo.findText(algo.capitalize())
            if idx >= 0:
                self._heat_algo_combo.setCurrentIndex(idx)
            self._chk_show_stats.setChecked(opts.get("show_stats", True))
            self._chk_use_current.setChecked(opts.get("use_current_stats", False))
            self._chk_add_mutation.setChecked(opts.get("add_mutation_stats", False))
            self._chk_hide_oos.setChecked(opts.get("hide_out_of_scope", False))

            # Scope
            self._chk_all_cats.setChecked(opts.get("all_cats", True))
            scope_state = opts.get("scope", {})
            for rk, cb in self._room_checkboxes.items():
                if rk in scope_state:
                    cb.setChecked(scope_state[rk])

            # Filters
            filters_dict = opts.get("filters")
            if filters_dict:
                self._filter_state = FilterState.from_dict(filters_dict)
                self._update_filter_summary()

            # Sort
            sort_col = opts.get("sort_col", -1)
            sort_desc = opts.get("sort_desc", True)
            if sort_col >= 0:
                order = Qt.DescendingOrder if sort_desc else Qt.AscendingOrder
                self._table.sortByColumn(sort_col, order)

            # Splitter
            sizes = opts.get("splitter_sizes")
            if sizes and len(sizes) == 3:
                self._splitter.setSizes(sizes)

        self._suppress_recompute = False
        self._mark_dirty(clear_results=True, cancel_running=True)

    def _schedule_save(self):
        self._save_timer.start()

    def _do_save(self):
        self._save_to_trait_ratings()
        if self._trait_ratings:
            self._trait_ratings.save()


# ── Filter Dialog ─────────────────────────────────────────────────────────────

class FilterDialog(QDialog):
    """Modal dialog for configuring score table filters."""

    def __init__(self, current: FilterState, cats: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Score Filters")
        self.setMinimumWidth(480)
        self.setStyleSheet(
            "QDialog { background:#0a0a18; color:#d7d7e6; }"
            "QCheckBox { color:#bbb; }"
            "QLabel { color:#bbb; }"
            "QComboBox { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:2px 6px; }"
            "QSpinBox, QDoubleSpinBox { background:#0d0d1c; color:#ccc;"
            " border:1px solid #2a2a4a; border-radius:4px; padding:2px 6px; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:6px 16px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
        )

        self._fs = FilterState()
        # Copy from current
        d = current.to_dict()
        self._fs = FilterState.from_dict(d)

        vb = QVBoxLayout(self)
        vb.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(6)
        row = 0

        ops = ["Less Than", "Equals", "Greater Than"]

        # Age
        self._age_chk = QCheckBox("Age")
        self._age_chk.setChecked(self._fs.age_active)
        self._age_op = QComboBox()
        self._age_op.addItems(ops)
        self._age_op.setCurrentText(self._fs.age_op)
        self._age_val = QSpinBox()
        self._age_val.setRange(0, 100)
        self._age_val.setValue(self._fs.age_value)
        grid.addWidget(self._age_chk, row, 0)
        grid.addWidget(self._age_op, row, 1)
        grid.addWidget(self._age_val, row, 2)
        row += 1

        # Gender
        self._gender_chk = QCheckBox("Gender")
        self._gender_chk.setChecked(self._fs.gender_active)
        self._gender_m = QCheckBox("M")
        self._gender_m.setChecked(self._fs.gender_male)
        self._gender_f = QCheckBox("F")
        self._gender_f.setChecked(self._fs.gender_female)
        self._gender_q = QCheckBox("?")
        self._gender_q.setChecked(self._fs.gender_unknown)
        gender_row = QHBoxLayout()
        gender_row.addWidget(self._gender_m)
        gender_row.addWidget(self._gender_f)
        gender_row.addWidget(self._gender_q)
        grid.addWidget(self._gender_chk, row, 0)
        grid.addLayout(gender_row, row, 1, 1, 2)
        row += 1

        # Score
        self._score_chk = QCheckBox("Score")
        self._score_chk.setChecked(self._fs.score_active)
        self._score_op = QComboBox()
        self._score_op.addItems(ops)
        self._score_op.setCurrentText(self._fs.score_op)
        self._score_val = QDoubleSpinBox()
        self._score_val.setRange(-100, 100)
        self._score_val.setValue(self._fs.score_value)
        grid.addWidget(self._score_chk, row, 0)
        grid.addWidget(self._score_op, row, 1)
        grid.addWidget(self._score_val, row, 2)
        row += 1

        # Stat sum
        self._sum_chk = QCheckBox("Stat Sum")
        self._sum_chk.setChecked(self._fs.sum_active)
        self._sum_op = QComboBox()
        self._sum_op.addItems(ops)
        self._sum_op.setCurrentText(self._fs.sum_op)
        self._sum_val = QSpinBox()
        self._sum_val.setRange(0, 100)
        self._sum_val.setValue(self._fs.sum_value)
        grid.addWidget(self._sum_chk, row, 0)
        grid.addWidget(self._sum_op, row, 1)
        grid.addWidget(self._sum_val, row, 2)
        row += 1

        # 7-count
        self._count7_chk = QCheckBox("7-count")
        self._count7_chk.setChecked(self._fs.count7_active)
        self._count7_op = QComboBox()
        self._count7_op.addItems(ops)
        self._count7_op.setCurrentText(self._fs.count7_op)
        self._count7_val = QSpinBox()
        self._count7_val.setRange(0, 7)
        self._count7_val.setValue(self._fs.count7_value)
        grid.addWidget(self._count7_chk, row, 0)
        grid.addWidget(self._count7_op, row, 1)
        grid.addWidget(self._count7_val, row, 2)
        row += 1

        # Injury
        self._injury_chk = QCheckBox("Has injuries")
        self._injury_chk.setChecked(self._fs.injury_active)
        grid.addWidget(self._injury_chk, row, 0, 1, 3)
        row += 1

        vb.addLayout(grid)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(clear_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(apply_btn)
        vb.addLayout(btn_row)

    def _clear_all(self):
        self._age_chk.setChecked(False)
        self._gender_chk.setChecked(False)
        self._score_chk.setChecked(False)
        self._sum_chk.setChecked(False)
        self._count7_chk.setChecked(False)
        self._injury_chk.setChecked(False)

    def result_state(self) -> FilterState:
        fs = FilterState()
        fs.age_active = self._age_chk.isChecked()
        fs.age_op = self._age_op.currentText()
        fs.age_value = self._age_val.value()
        fs.gender_active = self._gender_chk.isChecked()
        fs.gender_male = self._gender_m.isChecked()
        fs.gender_female = self._gender_f.isChecked()
        fs.gender_unknown = self._gender_q.isChecked()
        fs.score_active = self._score_chk.isChecked()
        fs.score_op = self._score_op.currentText()
        fs.score_value = self._score_val.value()
        fs.sum_active = self._sum_chk.isChecked()
        fs.sum_op = self._sum_op.currentText()
        fs.sum_value = self._sum_val.value()
        fs.count7_active = self._count7_chk.isChecked()
        fs.count7_op = self._count7_op.currentText()
        fs.count7_value = self._count7_val.value()
        fs.injury_active = self._injury_chk.isChecked()
        return fs
