from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QStyledItemDelegate,
    QStyle, QStyleOptionViewItem, QAbstractItemView, QHeaderView,
    QPushButton, QMenu,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QBrush, QPalette

from save_parser import (
    Cat, STAT_NAMES, can_breed, risk_percent, shared_ancestor_counts, _ancestor_depths,
)
from breeding import score_pair, PairFactors
from mewgenics.models.breeding_cache import BreedingCache
from mewgenics.utils.localization import _tr
from mewgenics.utils.tags import _cat_tags, _make_tag_icon
from mewgenics.utils.styling import _enforce_min_font_in_widget_tree


class SafeBreedingView(QWidget):
    """Dedicated view for ranking alive breeding candidates."""
    class _ColumnPaddingDelegate(QStyledItemDelegate):
        def __init__(self, extra_width: int, left_padding: int = 0, parent=None):
            super().__init__(parent)
            self._extra_width = extra_width
            self._left_padding = left_padding

        def sizeHint(self, option, index):
            s = super().sizeHint(option, index)
            return QSize(s.width() + self._extra_width, s.height())

        def paint(self, painter, option, index):
            if self._left_padding <= 0:
                return super().paint(painter, option, index)

            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            style = opt.widget.style() if opt.widget is not None else QApplication.style()

            text = opt.text
            opt.text = ""
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

            text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget).adjusted(
                self._left_padding, 0, 0, 0
            )
            if opt.textElideMode != Qt.ElideNone:
                text = opt.fontMetrics.elidedText(text, opt.textElideMode, text_rect.width())

            painter.save()
            if opt.state & QStyle.State_Selected:
                painter.setPen(opt.palette.color(QPalette.HighlightedText))
            else:
                painter.setPen(opt.palette.color(QPalette.Text))
            painter.setFont(opt.font)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
            painter.restore()

    @staticmethod
    def _mode_button_style(active: bool, background: str, border: str) -> str:
        if active:
            return (
                "QPushButton { "
                f"background:{background}; color:#f5fbff; border:1px solid {border};"
                " border-radius:4px; padding:4px 10px; font-weight:bold; }"
                f"QPushButton:hover {{ background:{background}; }}"
            )
        return (
            "QPushButton { background:#141428; color:#8f95bd; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 10px; }"
            "QPushButton:hover { background:#1e1e38; color:#ddd; }"
        )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget { background:#0a0a18; }"
            "QLabel { color:#bbb; }"
            "QListWidget { background:#0d0d1c; color:#ddd; border:1px solid #1e1e38; }"
            "QLineEdit { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 8px; }"
            "QTableWidget { background:#101023; color:#ddd; border:1px solid #26264a; }"
            "QHeaderView::section { background:#151532; color:#7d8bb0; border:none; padding:4px; font-weight:bold; }"
        )
        self._cats: list[Cat] = []
        self._alive: list[Cat] = []
        self._by_key: dict[int, Cat] = {}
        self._table_row_cat_keys: list[int] = []
        self._cache: Optional[BreedingCache] = None
        self._quality_mode: bool = False
        self._lover_key_map: dict[int, set[int]] = {}
        self._hater_key_map: dict[int, set[int]] = {}
        self._parent_key_map: dict[int, set[int]] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QWidget()
        left.setFixedWidth(320)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        self._list_title = QLabel(styleSheet="color:#666; font-size:10px; font-weight:bold;")
        lv.addWidget(self._list_title)
        self._search = QLineEdit()
        lv.addWidget(self._search)
        self._list = QListWidget()
        self._list.setIconSize(QSize(60, 20))
        lv.addWidget(self._list, 1)
        root.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)
        self._title = QLabel()
        self._title.setStyleSheet("color:#ddd; font-size:16px; font-weight:bold;")
        self._summary = QLabel("")
        self._summary.setStyleSheet("color:#666; font-size:11px;")
        self._mode_bar = QWidget()
        mode_layout = QHBoxLayout(self._mode_bar)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)
        mode_layout.addWidget(QLabel("Mode:"))
        self._quality_btn = QPushButton("Best Pair")
        self._quality_btn.setCheckable(True)
        self._quality_btn.clicked.connect(lambda: self.set_quality_mode(True))
        mode_layout.addWidget(self._quality_btn)
        self._risk_btn = QPushButton("Safe Pair")
        self._risk_btn.setCheckable(True)
        self._risk_btn.clicked.connect(lambda: self.set_quality_mode(False))
        mode_layout.addWidget(self._risk_btn)
        mode_layout.addStretch(1)

        self._table = QTableWidget(0, 7)
        self._table.setIconSize(QSize(60, 20))
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(True)
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Interactive)
        self._table.setItemDelegateForColumn(0, SafeBreedingView._ColumnPaddingDelegate(24, 8, self._table))
        self._table.setColumnWidth(0, 180)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 78)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 115)
        self._table.setColumnWidth(5, 110)
        self._table.setColumnWidth(6, 180)
        self._table.horizontalHeader().setSortIndicatorShown(False)

        rv.addWidget(self._mode_bar)
        rv.addWidget(self._title)
        rv.addWidget(self._summary)
        rv.addWidget(self._table, 1)
        root.addWidget(right, 1)

        self._search.textChanged.connect(self._refresh_list)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        self._table.cellClicked.connect(self._on_table_row_clicked)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self.retranslate_ui()
        self.set_quality_mode(True, refresh=False)
        _enforce_min_font_in_widget_tree(self)

    def retranslate_ui(self):
        self._list_title.setText(_tr("safe_breeding.list_title"))
        self._search.setPlaceholderText(_tr("safe_breeding.search_placeholder"))
        self._update_mode_controls()
        self._apply_mode_headers()
        self._refresh_list()

    def _update_mode_controls(self):
        risk_active = not self._quality_mode
        quality_active = self._quality_mode
        self._risk_btn.blockSignals(True)
        self._quality_btn.blockSignals(True)
        try:
            self._risk_btn.setChecked(risk_active)
            self._quality_btn.setChecked(quality_active)
        finally:
            self._risk_btn.blockSignals(False)
            self._quality_btn.blockSignals(False)
        self._risk_btn.setStyleSheet(self._mode_button_style(risk_active, "#1f5f4a", "#3f8f72"))
        self._quality_btn.setStyleSheet(self._mode_button_style(quality_active, "#2a3a5a", "#4a6a9a"))

    def _apply_mode_headers(self):
        if self._quality_mode:
            labels = [
                _tr("safe_breeding.table.cat", default="Partner"),
                _tr("safe_breeding.table.quality", default="Quality"),
                _tr("safe_breeding.table.risk"),
                "Stats + Sum",
                _tr("safe_breeding.table.complementarity", default="Complementarity"),
                _tr("safe_breeding.table.personality", default="Personality"),
                _tr("safe_breeding.table.notes", default="Notes"),
            ]
            self._table.verticalHeader().setDefaultSectionSize(38)
            self._table.setColumnWidth(0, 168)
            self._table.setColumnWidth(1, 72)
            self._table.setColumnWidth(2, 60)
            self._table.setColumnWidth(3, 228)
            self._table.setColumnWidth(4, 96)
            self._table.setColumnWidth(5, 90)
            self._table.setColumnWidth(6, 168)
            for col in range(4, 7):
                self._table.setColumnHidden(col, False)
        else:
            labels = [
                _tr("safe_breeding.table.cat", default="Partner"),
                _tr("safe_breeding.table.risk"),
                _tr("safe_breeding.table.shared_ancestors"),
                _tr("safe_breeding.table.child_outcome"),
                "",
                "",
                "",
            ]
            self._table.verticalHeader().setDefaultSectionSize(22)
            self._table.setColumnWidth(0, 180)
            self._table.setColumnWidth(1, 86)
            self._table.setColumnWidth(2, 94)
            self._table.setColumnWidth(3, 120)
            for col in range(4, 7):
                self._table.setColumnHidden(col, True)
        self._table.setHorizontalHeaderLabels(labels)

    @staticmethod
    def _expected_stats_caption(projection: dict) -> str:
        expected_stats = projection.get("expected_stats", {})
        first_line: list[str] = []
        second_line: list[str] = []
        for stat in STAT_NAMES[:4]:
            value = float(expected_stats.get(stat, 0.0))
            first_line.append(f"{stat} {value:.1f}")
        for stat in STAT_NAMES[4:]:
            value = float(expected_stats.get(stat, 0.0))
            second_line.append(f"{stat} {value:.1f}")
        total = sum(float(expected_stats.get(stat, 0.0)) for stat in STAT_NAMES)
        return "\n".join([
            " | ".join(first_line),
            " | ".join(second_line) + f" | Sum {total:.1f}",
        ])

    @staticmethod
    def _expected_stats_tooltip(projection: dict) -> str:
        expected_stats = projection.get("expected_stats", {})
        stat_ranges = projection.get("stat_ranges", {})
        lines = ["Projected stats:"]
        for stat in STAT_NAMES:
            lo, hi = stat_ranges.get(stat, (0, 0))
            expected = float(expected_stats.get(stat, hi))
            lines.append(f"{stat}: {lo}-{hi} (expected {expected:.1f})")
        sum_lo, sum_hi = projection.get("sum_range", (0, 0))
        lines.append(f"Sum range: {sum_lo}-{sum_hi}")
        return "\n".join(lines)

    def set_quality_mode(self, enabled: bool, refresh: bool = True):
        enabled = bool(enabled)
        if self._quality_mode == enabled and refresh:
            self._update_mode_controls()
            self._apply_mode_headers()
            self._refresh_list()
            return
        self._quality_mode = enabled
        self._update_mode_controls()
        self._apply_mode_headers()
        if refresh:
            self._refresh_list()

    def _focused_cat(self) -> Optional[Cat]:
        current = self._list.currentItem()
        if current is None:
            return None
        return self._by_key.get(int(current.data(Qt.UserRole)))

    def _pair_stimulation(self) -> float:
        try:
            from mewgenics.utils.config import _load_app_config
            value = _load_app_config().get("pair_stimulation", 50)
            return float(value if value is not None else 50)
        except Exception:
            return 50.0

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._table_row_cat_keys):
            return
        cat = self._by_key.get(self._table_row_cat_keys[row])
        if cat is None:
            return

        menu = QMenu(self)
        open_tree = menu.addAction("Open Family Tree")
        find_best = menu.addAction(_tr("menu.context.find_best_pair", default="Find Best Pair"))
        planner = menu.addAction("Jump to Planner")
        menu.addSeparator()
        toggle_pin = menu.addAction("Toggle Pin")
        toggle_mb = menu.addAction("Toggle Must Breed")
        toggle_block = menu.addAction("Toggle Block")

        window = self.window()
        open_tree.triggered.connect(lambda: getattr(window, "_open_tree_for_cat", lambda _cat: None)(cat))
        find_best.triggered.connect(lambda: getattr(window, "_open_safe_breeding_for_cat", lambda _cat, quality=None: None)(cat, quality=True))
        planner.triggered.connect(lambda: getattr(window, "_open_perfect_planner_for_cat", lambda _cat: None)(cat))
        toggle_pin.triggered.connect(lambda: getattr(window, "_toggle_single_cat_pin", lambda _cat: None)(cat))
        toggle_mb.triggered.connect(lambda: getattr(window, "_toggle_single_cat_must_breed", lambda _cat: None)(cat))
        toggle_block.triggered.connect(lambda: getattr(window, "_toggle_single_cat_blacklist", lambda _cat: None)(cat))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def set_cats(self, cats: list[Cat]):
        selected_key = None
        cur = self._list.currentItem()
        if cur is not None:
            selected_key = int(cur.data(Qt.UserRole))
        self._cats = cats
        self._alive = sorted([c for c in cats if c.status != "Gone"], key=lambda c: (c.name or "").lower())
        self._by_key = {c.db_key: c for c in self._alive}
        self._lover_key_map = {
            cat.db_key: {
                lover.db_key
                for lover in getattr(cat, "lovers", [])
                if lover is not None and getattr(lover, "db_key", None) is not None and lover is not cat
            }
            for cat in self._alive
        }
        self._hater_key_map = {
            cat.db_key: {
                hater.db_key
                for hater in getattr(cat, "haters", [])
                if hater is not None and getattr(hater, "db_key", None) is not None and hater is not cat
            }
            for cat in self._alive
        }
        self._parent_key_map = {
            cat.db_key: {
                parent.db_key
                for parent in (getattr(cat, "parent_a", None), getattr(cat, "parent_b", None))
                if parent is not None and getattr(parent, "db_key", None) is not None
            }
            for cat in self._alive
        }
        self._refresh_list()
        if selected_key is not None and selected_key in self._by_key:
            self.select_cat(self._by_key[selected_key])
        elif self._list.count():
            self._list.setCurrentRow(0)
        else:
            self._render_for(None)

    def set_cache(self, cache: Optional['BreedingCache']):
        self._cache = cache
        # Re-render the currently selected cat with cached data
        cur = self._list.currentItem()
        if cur is not None:
            self._render_for(self._by_key.get(int(cur.data(Qt.UserRole))))

    def select_cat(self, cat: Optional[Cat]):
        if cat is None or cat.db_key not in self._by_key:
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            if int(item.data(Qt.UserRole)) == cat.db_key:
                self._list.setCurrentRow(i)
                self._list.scrollToItem(item)
                return

    def _refresh_list(self):
        query = self._search.text().strip().lower()
        current_key = None
        cur = self._list.currentItem()
        if cur is not None:
            current_key = int(cur.data(Qt.UserRole))

        self._list.clear()
        for cat in self._alive:
            if query and query not in cat.name.lower():
                continue
            text = f"{cat.name}  ({cat.gender_display})"
            if cat.is_blacklisted:
                text += f"  [{_tr('safe_breeding.list.blocked')}]"
            if cat.must_breed:
                text += f"  [{_tr('safe_breeding.list.must')}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, cat.db_key)
            icon = _make_tag_icon(_cat_tags(cat), dot_size=10, spacing=3)
            if not icon.isNull():
                item.setIcon(icon)
            if cat.is_blacklisted:
                item.setForeground(QBrush(QColor(170, 100, 100)))
            if cat.must_breed:
                item.setForeground(QBrush(QColor(98, 194, 135)))
            self._list.addItem(item)
        if self._list.count() == 0:
            self._render_for(None)
            return
        if current_key is not None:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if int(item.data(Qt.UserRole)) == current_key:
                    self._list.setCurrentRow(i)
                    return
        self._list.setCurrentRow(0)

    def _on_current_item_changed(self, current, previous):
        if current is None:
            self._render_for(None)
            return
        self._render_for(self._by_key.get(int(current.data(Qt.UserRole))))

    def _on_table_row_clicked(self, row: int, _column: int):
        if row < 0 or row >= len(self._table_row_cat_keys):
            return
        cat = self._by_key.get(self._table_row_cat_keys[row])
        if cat is not None:
            self.select_cat(cat)

    def _render_for(self, cat: Optional[Cat]):
        # This view is a ranking table. Keep sorting disabled so row indices
        # remain stable while we populate all columns for each candidate.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table_row_cat_keys = []
        if cat is None:
            self._title.setText("Mating Pair Search")
            self._summary.setText(_tr("safe_breeding.summary_empty"))
            self._apply_mode_headers()
            return

        cache = self._cache
        self._title.setText(f"Mating Pair Search for {cat.name}")

        candidates: list[dict[str, object]] = []
        for other in self._alive:
            if other is cat:
                continue
            ok, _ = can_breed(cat, other)
            if not ok:
                continue
            if cache is not None and cache.ready:
                shared, recent_shared = cache.get_shared(cat, other, recent_depth=3)
                rel = cache.get_risk(cat, other)
            else:
                shared, recent_shared = shared_ancestor_counts(cat, other, recent_depth=3)
                rel = risk_percent(cat, other)
            quality_factors: Optional[PairFactors] = None
            if self._quality_mode:
                quality_factors = score_pair(
                    cat,
                    other,
                    hater_key_map=getattr(self, "_hater_key_map", {}),
                    lover_key_map=getattr(self, "_lover_key_map", {}),
                    parent_key_map=getattr(self, "_parent_key_map", {}),
                    cache=cache,
                    stimulation=self._pair_stimulation(),
                )
                if not quality_factors.compatible:
                    continue
            closest_recent_gen = 0
            if recent_shared:
                if cache is not None and cache.ready:
                    da = cache.get_ancestor_depths_for(cat)
                    db = cache.get_ancestor_depths_for(other)
                else:
                    da = _ancestor_depths(cat, max_depth=8)
                    db = _ancestor_depths(other, max_depth=8)
                common = set(da.keys()) & set(db.keys())
                recent_levels = [
                    max(da[anc], db[anc])
                    for anc in common
                    if da[anc] <= 3 and db[anc] <= 3
                ]
                closest_recent_gen = min(recent_levels) if recent_levels else 3

            lover_keys = {
                lover.db_key
                for lover in getattr(cat, "lovers", [])
                if lover is not None and getattr(lover, "db_key", None) is not None
            }
            is_loved = other.db_key in lover_keys
            is_mutual_love = is_loved and cat.db_key in {
                lover.db_key
                for lover in getattr(other, "lovers", [])
                if lover is not None and getattr(lover, "db_key", None) is not None
            }

            row_bg = None
            row_fg = None
            if is_mutual_love:
                row_bg = QColor(132, 36, 88)
                row_fg = QColor(246, 229, 239)
            elif is_loved:
                row_bg = QColor(224, 176, 201)
                row_fg = QColor(52, 32, 44)

            notes: list[str] = []
            if shared:
                notes.append(_tr("safe_breeding.notes.shared", default="Shared ancestors: {count}", count=shared))
            if recent_shared:
                notes.append(_tr("safe_breeding.notes.recent_shared", default="Recent shared: {count}", count=recent_shared))
            if is_mutual_love:
                notes.append(_tr("safe_breeding.notes.mutual_lovers", default="Mutual lovers"))
            elif is_loved:
                notes.append(_tr("safe_breeding.notes.loved", default="Lover pair"))

            if self._quality_mode and quality_factors is not None:
                expected_sum = sum(quality_factors.projection.expected_stats.values())
                if quality_factors.must_breed_bonus:
                    notes.append(_tr("safe_breeding.notes.must_breed", default="Must breed"))
                if quality_factors.lover_bonus:
                    notes.append(_tr("safe_breeding.notes.mutual_lovers", default="Mutual lovers"))
                if quality_factors.trait_bonus:
                    notes.append(_tr("safe_breeding.notes.trait_bonus", default="Trait bonus: {value:.1f}", value=quality_factors.trait_bonus))
                if quality_factors.variance_penalty:
                    notes.append(_tr("safe_breeding.notes.variance_penalty", default="Variance penalty: {value:.1f}", value=quality_factors.variance_penalty))
                candidates.append({
                    "cat": other,
                    "quality": float(quality_factors.quality),
                    "risk": float(rel),
                    "projection": quality_factors.projection,
                    "expected_sum": float(expected_sum),
                    "complementarity": float(quality_factors.complementarity_bonus),
                    "personality": float(quality_factors.personality_bonus),
                    "notes": notes,
                    "row_bg": row_bg,
                    "row_fg": row_fg,
                })
            else:
                candidates.append({
                    "cat": other,
                    "risk": float(rel),
                    "shared": int(shared),
                    "closest_recent_gen": int(closest_recent_gen),
                    "notes": notes,
                    "row_bg": row_bg,
                    "row_fg": row_fg,
                })

        if self._quality_mode:
            candidates.sort(key=lambda item: (-float(item["quality"]), float(item["risk"]), (item["cat"].name or "").lower()))
        else:
            candidates.sort(key=lambda item: (float(item["risk"]), int(item["shared"]) * 1000 + int(item["closest_recent_gen"]), (item["cat"].name or "").lower()))

        self._summary.setText(_tr(
            "safe_breeding.summary_quality" if self._quality_mode else "safe_breeding.summary",
            default="Quality-ranked compatible mates: {count}" if self._quality_mode else "Compatible mates: {count}",
            count=len(candidates),
        ))
        self._table.setRowCount(len(candidates))
        for row, item in enumerate(candidates):
            other = item["cat"]
            self._table_row_cat_keys.append(other.db_key)
            row_bg = item.get("row_bg")
            row_fg = item.get("row_fg")
            name_text = f"{other.name} ({other.gender_display})"
            if item.get("quality") is None:
                risk_pct = int(round(float(item["risk"])))
                if risk_pct >= 100:
                    tag, risk_color = _tr("safe_breeding.tag.highly_inbred"), QColor(217, 119, 119)
                elif risk_pct >= 50:
                    tag, risk_color = _tr("safe_breeding.tag.moderately_inbred"), QColor(216, 181, 106)
                elif risk_pct >= 20:
                    tag, risk_color = _tr("safe_breeding.tag.slightly_inbred"), QColor(143, 201, 230)
                else:
                    tag, risk_color = _tr("safe_breeding.tag.not_inbred"), QColor(98, 194, 135)
                heart = " ♥" if item.get("notes") and any("Lover" in note or "lovers" in note.lower() for note in item["notes"]) else ""
                name_item = QTableWidgetItem(f"{other.name}{heart} ({other.gender_display})")
                icon = _make_tag_icon(_cat_tags(other), dot_size=14, spacing=4)
                if not icon.isNull():
                    name_item.setIcon(icon)
                risk_item = QTableWidgetItem(f"{risk_pct}%")
                shared_item = QTableWidgetItem(str(item["shared"]))
                outcome_item = QTableWidgetItem(tag)
                risk_item.setData(Qt.UserRole, risk_pct)
                shared_item.setData(Qt.UserRole, item["shared"])
                for it in (name_item, risk_item, shared_item, outcome_item):
                    it.setTextAlignment(Qt.AlignCenter)
                    if row_bg is not None:
                        it.setBackground(QBrush(row_bg))
                        if row_fg is not None:
                            it.setForeground(QBrush(row_fg))
                outcome_item.setForeground(QBrush(risk_color))
                self._table.setItem(row, 0, name_item)
                self._table.setItem(row, 1, risk_item)
                self._table.setItem(row, 2, shared_item)
                self._table.setItem(row, 3, outcome_item)
                continue

            quality_item = QTableWidgetItem(f"{float(item['quality']):.1f}")
            risk_pct = int(round(float(item["risk"])))
            risk_item = QTableWidgetItem(f"{risk_pct}%")
            expected_item = QTableWidgetItem(self._expected_stats_caption(item["projection"]))
            complementarity_item = QTableWidgetItem(f"{float(item['complementarity']):.1f}")
            personality_item = QTableWidgetItem(f"{float(item['personality']):.1f}")
            notes_item = QTableWidgetItem("; ".join(item.get("notes", [])) or "—")
            if row_bg is not None:
                for it in (quality_item, risk_item, expected_item, complementarity_item, personality_item, notes_item):
                    it.setBackground(QBrush(row_bg))
                    if row_fg is not None:
                        it.setForeground(QBrush(row_fg))
            icon = _make_tag_icon(_cat_tags(other), dot_size=14, spacing=4)
            name_item = QTableWidgetItem(name_text)
            if not icon.isNull():
                name_item.setIcon(icon)
            for it in (name_item, quality_item, risk_item, expected_item, complementarity_item, personality_item):
                it.setTextAlignment(Qt.AlignCenter)
            expected_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            notes_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            font = quality_item.font()
            font.setBold(True)
            quality_item.setFont(font)
            if row_fg is None:
                quality_item.setForeground(QBrush(QColor(98, 194, 135)))
            risk_item.setData(Qt.UserRole, risk_pct)
            expected_item.setData(Qt.UserRole, float(item["expected_sum"]))
            expected_item.setToolTip(self._expected_stats_tooltip(item["projection"]))
            if row_fg is None:
                risk_item.setForeground(QBrush(QColor(216, 181, 106)))
            quality_item.setToolTip(
                _tr(
                    "safe_breeding.quality_tooltip",
                    default="Quality is a blend of offspring stat expectations, complementarity, personality, and bonus signals.",
                )
            )
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, quality_item)
            self._table.setItem(row, 2, risk_item)
            self._table.setItem(row, 3, expected_item)
            self._table.setItem(row, 4, complementarity_item)
            self._table.setItem(row, 5, personality_item)
            self._table.setItem(row, 6, notes_item)

        self._apply_mode_headers()
