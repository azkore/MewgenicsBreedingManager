from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QSizePolicy, QHeaderView, QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QBrush, QFont

from save_parser import Cat
from breeding import is_mutual_lover_pair
from mewgenics.utils.localization import _tr
from mewgenics.utils.tags import _cat_tags, _make_tag_icon
from mewgenics.utils.styling import _enforce_min_font_in_widget_tree


class BreedingPartnersView(QWidget):
    """Dedicated view for mutual and one-way lover rows plus room mismatch hints."""

    COL_RELATION = 0
    COL_CAT_A = 1
    COL_CAT_B = 2
    COL_ROOM_A = 3
    COL_ROOM_B = 4
    COL_STATUS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget { background:#0a0a18; }"
            "QLabel { color:#bbb; }"
            "QLineEdit { background:#0d0d1c; color:#ccc; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:4px 8px; }"
            "QTableWidget { background:#101023; color:#ddd; border:1px solid #26264a; }"
            "QHeaderView::section { background:#151532; color:#7d8bb0; border:none; padding:4px; font-weight:bold; }"
        )
        self._cats: list[Cat] = []
        self._pairs: list[dict[str, object]] = []
        self._all_by_key: dict[int, Cat] = {}
        self._navigate_to_cat_callback = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setStyleSheet("color:#ddd; font-size:18px; font-weight:bold;")
        self._summary = QLabel("")
        self._summary.setStyleSheet("color:#666; font-size:11px;")
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(self._summary)
        root.addLayout(header)

        self._search = QLineEdit()
        root.addWidget(self._search)

        self._table = QTableWidget(0, 6)
        self._table.setIconSize(QSize(60, 20))
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._table.setHorizontalHeaderLabels([
            _tr("breeding_partners.table.relation"),
            _tr("breeding_partners.table.cat_a"),
            _tr("breeding_partners.table.cat_b"),
            _tr("breeding_partners.table.room_a"),
            _tr("breeding_partners.table.room_b"),
            _tr("breeding_partners.table.status"),
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSortIndicatorShown(True)
        hh.setSectionResizeMode(self.COL_RELATION, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_CAT_A, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_CAT_B, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_ROOM_A, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_ROOM_B, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        self._table.setColumnWidth(self.COL_RELATION, 110)
        self._table.setColumnWidth(self.COL_CAT_A, 160)
        self._table.setColumnWidth(self.COL_CAT_B, 160)
        self._table.setColumnWidth(self.COL_ROOM_A, 110)
        self._table.setColumnWidth(self.COL_ROOM_B, 110)
        self._table.setColumnWidth(self.COL_STATUS, 280)
        root.addWidget(self._table, 1)

        self._search.textChanged.connect(self._refresh_table)
        self._table.itemClicked.connect(self._on_cat_cell_clicked)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        _enforce_min_font_in_widget_tree(self)
        self._table.sortByColumn(self.COL_RELATION, Qt.AscendingOrder)
        self.retranslate_ui()

    def _cat_label(self, cat, *, hide_gone: bool = False) -> str:
        if hide_gone and cat.status == "Gone":
            return ""
        label = f"{cat.name} ({cat.gender_display})"
        if cat.status == "Gone":
            label += " (gone)"
        return label

    def _cat_room_label(self, cat) -> str:
        if cat.status == "In House":
            return cat.room_display or _tr("status.in_house", default="In House")
        if cat.status == "Gone":
            return _tr("status.gone", default="Gone")
        return _tr("status.adventure", default="Away")

    def _cat_status_label(self, cat) -> str:
        label = cat.name
        if cat.status == "Gone":
            label += " (gone)"
        return label

    def _relation_label(self, is_mutual: bool) -> str:
        return _tr(
            "breeding_partners.relation.mutual" if is_mutual else "breeding_partners.relation.one_way",
            default="Mutual" if is_mutual else "One way",
        )

    def _love_status_text(self, cat_a, cat_b, is_mutual: bool) -> str:
        cat_a_label = self._cat_status_label(cat_a)
        cat_b_label = self._cat_status_label(cat_b)
        if is_mutual:
            return f"{cat_a_label} <-> {cat_b_label}"
        return f"{cat_a_label} --> {cat_b_label}"

    def set_navigate_to_cat_callback(self, callback):
        self._navigate_to_cat_callback = callback

    def set_cats(self, cats: list[Cat]):
        self._cats = cats
        self._pairs = []
        self._all_by_key = {cat.db_key: cat for cat in cats if cat is not None}
        seen: set[tuple[str, int, int]] = set()
        all_cats = [cat for cat in cats if cat is not None]
        cat_keys = {cat.db_key for cat in all_cats}
        lover_key_map: dict[int, set[int]] = {
            cat.db_key: {
                lover.db_key
                for lover in getattr(cat, "lovers", [])
                if lover is not None and getattr(lover, "db_key", None) is not None and lover is not cat
            }
            for cat in all_cats
        }
        for cat in all_cats:
            for lover in getattr(cat, "lovers", []):
                if lover is None or lover is cat or getattr(lover, "db_key", None) not in cat_keys:
                    continue
                mutual = is_mutual_lover_pair(cat, lover, lover_key_map)
                key = ("mutual",) + tuple(sorted((cat.db_key, lover.db_key))) if mutual else ("one_way", cat.db_key, lover.db_key)
                if key in seen:
                    continue
                seen.add(key)
                if mutual and cat.db_key > lover.db_key:
                    cat_a, cat_b = lover, cat
                else:
                    cat_a, cat_b = cat, lover
                same_room = bool(
                    cat_a.room
                    and cat_b.room
                    and cat_a.room == cat_b.room
                    and cat_a.status == cat_b.status == "In House"
                )
                self._pairs.append({
                    "cat_a": cat_a,
                    "cat_b": cat_b,
                    "same_room": same_room,
                    "is_mutual": mutual,
                })
        self._pairs.sort(key=lambda p: (
            not bool(p["is_mutual"]),
            not bool(p["same_room"]),
            str(p["cat_a"].name).lower(),
            str(p["cat_b"].name).lower(),
        ))
        self._refresh_table()

    def set_cache(self, cache: Optional['BreedingCache']):
        """Breeding pair detection does not depend on the shared breeding cache."""
        return None

    def _refresh_table(self):
        query = self._search.text().strip().lower()
        pairs = self._pairs
        if query:
            pairs = [
                p for p in pairs
                if query in " ".join([
                    self._relation_label(bool(p["is_mutual"])).lower(),
                    self._cat_label(p["cat_a"]).lower(),
                    self._cat_label(p["cat_b"]).lower(),
                    self._cat_room_label(p["cat_a"]).lower(),
                    self._cat_room_label(p["cat_b"]).lower(),
                    self._love_status_text(p["cat_a"], p["cat_b"], bool(p["is_mutual"])).lower(),
                ])
            ]
        pairs = [p for p in pairs if p["cat_a"].status != "Gone"]

        # Sorting is intentionally disabled here so row insertion order stays
        # deterministic while we rebuild the rows, then we restore the active sort.
        self._table.setSortingEnabled(False)
        sort_col = self._table.horizontalHeader().sortIndicatorSection()
        sort_order = self._table.horizontalHeader().sortIndicatorOrder()
        self._table.setRowCount(len(pairs))
        mismatch_count = 0
        mutual_count = 0
        for row, pair in enumerate(pairs):
            is_mutual = bool(pair["is_mutual"])
            if is_mutual:
                mutual_count += 1
            same_room = bool(pair["same_room"])
            if not same_room:
                mismatch_count += 1
            relation_text = self._relation_label(is_mutual)
            relation_color = QColor(98, 194, 135) if is_mutual else QColor(216, 181, 106)
            item_relation = QTableWidgetItem(relation_text)
            item_relation.setTextAlignment(Qt.AlignCenter)
            item_relation.setForeground(QBrush(relation_color))
            relation_font = item_relation.font()
            relation_font.setBold(True)
            item_relation.setFont(relation_font)
            item_relation.setData(Qt.UserRole, pair["cat_a"].db_key)

            item_a = QTableWidgetItem(self._cat_label(pair["cat_a"], hide_gone=True))
            link_font = QFont()
            link_font.setUnderline(True)
            item_a.setFont(link_font)
            item_a.setForeground(QBrush(QColor(100, 149, 237)))
            item_a.setData(Qt.UserRole, pair["cat_a"].db_key)
            if item_a.text():
                icon_a = _make_tag_icon(_cat_tags(pair['cat_a']), dot_size=14, spacing=4)
                if not icon_a.isNull():
                    item_a.setIcon(icon_a)
            item_b = QTableWidgetItem(self._cat_label(pair["cat_b"]))
            item_b.setFont(link_font)
            item_b.setForeground(QBrush(QColor(100, 149, 237)))
            item_b.setData(Qt.UserRole, pair["cat_b"].db_key)
            icon_b = _make_tag_icon(_cat_tags(pair['cat_b']), dot_size=14, spacing=4)
            if not icon_b.isNull():
                item_b.setIcon(icon_b)
            items = [
                item_relation,
                item_a,
                item_b,
                QTableWidgetItem(self._cat_room_label(pair["cat_a"])),
                QTableWidgetItem(self._cat_room_label(pair["cat_b"])),
                QTableWidgetItem(self._love_status_text(pair["cat_a"], pair["cat_b"], is_mutual)),
            ]
            items[self.COL_STATUS].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            items[self.COL_STATUS].setForeground(QBrush(relation_color))
            items[self.COL_ROOM_A].setData(Qt.UserRole, pair["cat_a"].db_key)
            items[self.COL_ROOM_B].setData(Qt.UserRole, pair["cat_b"].db_key)
            items[self.COL_STATUS].setData(Qt.UserRole, pair["cat_a"].db_key)
            if not same_room:
                for item in items[:5]:
                    item.setBackground(QBrush(QColor(48, 36, 14)))
            for col, item in enumerate(items):
                self._table.setItem(row, col, item)

        total = len(self._pairs)
        shown = len(pairs)
        self._table.setSortingEnabled(True)
        if sort_col != self.COL_RELATION or sort_order != Qt.AscendingOrder:
            self._table.sortByColumn(sort_col, sort_order)
        self._summary.setText(_tr("breeding_partners.summary",
                                   shown=shown, total=total, mutual=mutual_count, one_way=shown - mutual_count, mismatches=mismatch_count))

    def _on_cat_cell_clicked(self, item):
        """Handle clicks on cat names to navigate to the cat in the main view."""
        col = self._table.column(item)
        # Only handle clicks on Cat A or Cat B.
        if col not in (self.COL_CAT_A, self.COL_CAT_B):
            return

        cat_name = item.text()
        if not cat_name or not self._navigate_to_cat_callback:
            return

        # Call the navigate callback with the cat name
        self._navigate_to_cat_callback(cat_name)

    def _show_context_menu(self, pos):
        index = self._table.indexAt(pos)
        if not index.isValid():
            return

        item = self._table.item(index.row(), index.column())
        if item is None:
            return

        db_key = item.data(Qt.UserRole)
        if db_key is None and index.column() != self.COL_CAT_A:
            fallback = self._table.item(index.row(), self.COL_CAT_A)
            if fallback is not None:
                db_key = fallback.data(Qt.UserRole)
        if db_key is None:
            return

        cat = self._all_by_key.get(int(db_key))
        if cat is None:
            return

        window = self.window()
        menu = QMenu(self)
        open_tree = menu.addAction(_tr("menu.context.open_tree", default="Open Family Tree"))
        find_best = menu.addAction(_tr("menu.context.find_best_pair", default="Find Best Pair"))
        jump_planner = menu.addAction(_tr("menu.context.jump_planner", default="Jump to Planner"))
        menu.addSeparator()
        toggle_pin = menu.addAction(_tr("menu.context.toggle_pin", default="Toggle Pin"))
        toggle_mb = menu.addAction(_tr("menu.context.toggle_must_breed", default="Toggle Must Breed"))
        toggle_block = menu.addAction(_tr("menu.context.toggle_block", default="Toggle Block"))

        open_tree.triggered.connect(lambda: getattr(window, "_open_tree_for_cat", lambda _cat: None)(cat))
        find_best.triggered.connect(lambda: getattr(window, "_open_safe_breeding_for_cat", lambda _cat, quality=None: None)(cat, quality=True))
        jump_planner.triggered.connect(lambda: getattr(window, "_open_perfect_planner_for_cat", lambda _cat: None)(cat))
        toggle_pin.triggered.connect(lambda: getattr(window, "_toggle_single_cat_pin", lambda _cat: None)(cat))
        toggle_mb.triggered.connect(lambda: getattr(window, "_toggle_single_cat_must_breed", lambda _cat: None)(cat))
        toggle_block.triggered.connect(lambda: getattr(window, "_toggle_single_cat_blacklist", lambda _cat: None)(cat))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def retranslate_ui(self):
        self._title.setText(_tr("breeding_partners.title"))
        self._search.setPlaceholderText(_tr("breeding_partners.search_placeholder"))
        self._table.setHorizontalHeaderLabels([
            _tr("breeding_partners.table.relation"),
            _tr("breeding_partners.table.cat_a"),
            _tr("breeding_partners.table.cat_b"),
            _tr("breeding_partners.table.room_a"),
            _tr("breeding_partners.table.room_b"),
            _tr("breeding_partners.table.status"),
        ])
        self._refresh_table()
