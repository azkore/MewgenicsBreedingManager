"""Table view header/sort state persistence."""
import weakref
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableView, QHeaderView,
)
from PySide6.QtCore import Qt, QByteArray, QTimer
from PySide6.QtGui import QColor, QPalette

from mewgenics.constants import COL_ADV, COL_TAGS
from mewgenics.utils.config import _load_ui_state, _save_ui_state


_TABLE_VIEW_STATES_KEY = "table_view_states"
_TABLE_STATE_SAVE_TIMERS: "weakref.WeakKeyDictionary[QWidget, QTimer]" = weakref.WeakKeyDictionary()


def _table_view_state_key(widget: QWidget) -> str:
    parts: list[str] = []
    current: Optional[QWidget] = widget
    while current is not None:
        name = current.objectName().strip()
        if not name:
            name = current.__class__.__name__
            parent = current.parentWidget()
            if parent is not None:
                siblings = [child for child in parent.children() if isinstance(child, QWidget)]
                same_kind = [child for child in siblings if child.__class__ is current.__class__]
                if len(same_kind) > 1:
                    try:
                        name = f"{name}[{same_kind.index(current)}]"
                    except ValueError:
                        pass
        parts.append(name)
        current = current.parentWidget()
    return "/".join(reversed(parts))


def _load_table_view_states() -> dict:
    state = _load_ui_state(_TABLE_VIEW_STATES_KEY)
    return state if isinstance(state, dict) else {}


def _save_table_view_states(state: dict):
    _save_ui_state(_TABLE_VIEW_STATES_KEY, state if isinstance(state, dict) else {})


def _queue_table_view_state_save(widget: QWidget):
    timer = _TABLE_STATE_SAVE_TIMERS.get(widget)
    if timer is None:
        timer = QTimer(widget)
        timer.setSingleShot(True)
        timer.setInterval(200)
        timer.timeout.connect(lambda w=widget: _save_table_view_state(w))
        _TABLE_STATE_SAVE_TIMERS[widget] = timer
    timer.start()


def _save_table_view_state(widget: QWidget):
    if not isinstance(widget, (QTableWidget, QTableView)):
        return
    header = widget.horizontalHeader()
    key = _table_view_state_key(widget)
    state_version = widget.property("_table_state_version")
    try:
        state_version = int(state_version) if state_version is not None else 1
    except Exception:
        state_version = 1
    states = _load_table_view_states()
    states[key] = {
        "state_version": state_version,
        "header_state": header.saveState().toBase64().data().decode("ascii"),
        "sort_column": header.sortIndicatorSection(),
        "sort_order": int(header.sortIndicatorOrder().value),
        "sorting_enabled": bool(widget.isSortingEnabled()),
    }
    _save_table_view_states(states)


def _restore_table_view_state(widget: QWidget):
    if not isinstance(widget, (QTableWidget, QTableView)):
        return
    header = widget.horizontalHeader()
    key = _table_view_state_key(widget)
    state = _load_table_view_states().get(key)
    if not isinstance(state, dict):
        return
    expected_version = widget.property("_table_state_version")
    try:
        expected_version = int(expected_version) if expected_version is not None else 1
    except Exception:
        expected_version = 1
    state_version = state.get("state_version", 1)
    try:
        state_version = int(state_version)
    except Exception:
        state_version = 1
    header_state = state.get("header_state", "")
    if expected_version <= 1 or state_version == expected_version:
        if isinstance(header_state, str) and header_state:
            try:
                header.restoreState(QByteArray.fromBase64(header_state.encode("ascii")))
            except Exception:
                pass
    if bool(widget.property("_keep_tags_first")) and COL_TAGS < header.count():
        try:
            tags_visual = header.visualIndex(COL_TAGS)
            if tags_visual >= 0 and tags_visual != 0:
                header.moveSection(tags_visual, 0)
        except Exception:
            pass
    min_tags_width = widget.property("_min_tags_width")
    try:
        min_tags_width = int(min_tags_width) if min_tags_width is not None else 0
    except Exception:
        min_tags_width = 0
    if min_tags_width > 0 and COL_TAGS < header.count() and header.sectionSize(COL_TAGS) < min_tags_width:
        try:
            header.resizeSection(COL_TAGS, min_tags_width)
        except Exception:
            pass
    if bool(widget.property("_keep_adv_ready_last")) and COL_ADV < header.count():
        try:
            adv_visual = header.visualIndex(COL_ADV)
            if adv_visual >= 0 and adv_visual != header.count() - 1:
                header.moveSection(adv_visual, header.count() - 1)
        except Exception:
            pass
    sort_column = state.get("sort_column")
    if isinstance(sort_column, int) and sort_column >= 0:
        sort_order = Qt.SortOrder(int(state.get("sort_order", int(Qt.AscendingOrder.value))))
        try:
            if isinstance(widget, QTableWidget):
                widget.sortItems(sort_column, sort_order)
            else:
                widget.sortByColumn(sort_column, sort_order)
            header.setSortIndicatorShown(True)
            header.setSortIndicator(sort_column, sort_order)
        except Exception:
            pass


def _capture_table_view_states(root: Optional[QWidget]) -> dict[str, dict]:
    if root is None:
        return {}
    states: dict[str, dict] = {}
    for widget in [root] + root.findChildren(QWidget):
        if not isinstance(widget, (QTableWidget, QTableView)):
            continue
        header = widget.horizontalHeader()
        states[_table_view_state_key(widget)] = {
            "header_state": header.saveState().toBase64().data().decode("ascii"),
            "sort_column": header.sortIndicatorSection(),
            "sort_order": int(header.sortIndicatorOrder().value),
            "sorting_enabled": bool(widget.isSortingEnabled()),
        }
    return states


def _restore_table_view_states(root: Optional[QWidget], states: dict):
    if root is None or not isinstance(states, dict):
        return
    for widget in [root] + root.findChildren(QWidget):
        if not isinstance(widget, (QTableWidget, QTableView)):
            continue
        state = states.get(_table_view_state_key(widget))
        if not isinstance(state, dict):
            continue
        header = widget.horizontalHeader()
        widget.setSortingEnabled(bool(state.get("sorting_enabled", True)))
        expected_version = widget.property("_table_state_version")
        try:
            expected_version = int(expected_version) if expected_version is not None else 1
        except Exception:
            expected_version = 1
        state_version = state.get("state_version", 1)
        try:
            state_version = int(state_version)
        except Exception:
            state_version = 1
        header_state = state.get("header_state", "")
        if expected_version <= 1 or state_version == expected_version:
            if isinstance(header_state, str) and header_state:
                try:
                    header.restoreState(QByteArray.fromBase64(header_state.encode("ascii")))
                except Exception:
                    pass
        if bool(widget.property("_keep_tags_first")) and COL_TAGS < header.count():
            try:
                tags_visual = header.visualIndex(COL_TAGS)
                if tags_visual >= 0 and tags_visual != 0:
                    header.moveSection(tags_visual, 0)
            except Exception:
                pass
        min_tags_width = widget.property("_min_tags_width")
        try:
            min_tags_width = int(min_tags_width) if min_tags_width is not None else 0
        except Exception:
            min_tags_width = 0
        if min_tags_width > 0 and COL_TAGS < header.count() and header.sectionSize(COL_TAGS) < min_tags_width:
            try:
                header.resizeSection(COL_TAGS, min_tags_width)
            except Exception:
                pass
        if bool(widget.property("_keep_adv_ready_last")) and COL_ADV < header.count():
            try:
                adv_visual = header.visualIndex(COL_ADV)
                if adv_visual >= 0 and adv_visual != header.count() - 1:
                    header.moveSection(adv_visual, header.count() - 1)
            except Exception:
                pass
        sort_column = state.get("sort_column")
        if isinstance(sort_column, int) and sort_column >= 0:
            sort_order = Qt.SortOrder(int(state.get("sort_order", int(Qt.AscendingOrder.value))))
            try:
                if isinstance(widget, QTableWidget):
                    widget.sortItems(sort_column, sort_order)
                else:
                    widget.sortByColumn(sort_column, sort_order)
                header.setSortIndicatorShown(True)
                header.setSortIndicator(sort_column, sort_order)
            except Exception:
                pass


def _configure_table_view_behavior(widget: QWidget):
    if not isinstance(widget, (QTableWidget, QTableView)):
        return
    if widget.property("_global_table_behavior_ready"):
        return
    widget.setProperty("_global_table_behavior_ready", True)

    widget.setAlternatingRowColors(True)
    palette = widget.palette()
    palette.setColor(QPalette.AlternateBase, QColor(24, 27, 50))
    widget.setPalette(palette)

    header = widget.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionsMovable(True)
    header.setSortIndicatorShown(False)
    for col in range(header.count()):
        header.setSectionResizeMode(col, QHeaderView.Interactive)
    header.sectionResized.connect(lambda *_args, w=widget: _queue_table_view_state_save(w))
    header.sectionMoved.connect(lambda *_args, w=widget: _queue_table_view_state_save(w))
    header.sortIndicatorChanged.connect(lambda *_args, w=widget: _queue_table_view_state_save(w))
    _restore_table_view_state(widget)
