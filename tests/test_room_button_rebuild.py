"""Regression tests for _rebuild_room_buttons.

Guards the "menu tab won't switch after an in-game day + reload" bug:

  * QFileSystemWatcher fires when Mewgenics rewrites the save
  * _on_room_patch calls _rebuild_room_buttons, which deleteLater()s
    every old room QPushButton
  * If _active_btn and _room_btns still hold references to the deleted
    widgets, the next _filter() click raises RuntimeError on setChecked()
    mid-handler and aborts before set_room() runs — so the newly-clicked
    button highlights but the filter never changes.

The fix rescues the active room key across the rebuild and repoints
_active_btn at the freshly-created replacement button.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

try:
    from shiboken6 import isValid as _shiboken_is_valid
except ImportError:  # pragma: no cover — PySide6 always ships shiboken6
    _shiboken_is_valid = None

import mewgenics_manager as mm


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


def _make_cat(db_key: int, room: str, status: str = "In House"):
    return SimpleNamespace(db_key=db_key, room=room, status=status)


def _bare_window(qt_app):
    window = mm.MainWindow.__new__(mm.MainWindow)
    window._rooms_vb_host = QWidget()
    window._rooms_vb = QVBoxLayout(window._rooms_vb_host)
    window._room_btns = {}
    window._active_btn = None
    return window


class TestRebuildRescuesActiveRoom:
    def test_active_btn_repointed_to_new_button_for_same_room(self, qt_app):
        window = _bare_window(qt_app)
        cats = [
            _make_cat(1, "Attic"),
            _make_cat(2, "Floor1_Large"),
        ]
        mm.MainWindow._rebuild_room_buttons(window, cats)

        # Simulate a user having the Attic tab active.
        window._active_btn = window._room_btns["Attic"]
        old_attic_btn = window._active_btn

        # Rebuild (e.g., after a quick room refresh triggered by the
        # in-game day rolling over). The old Attic QPushButton is
        # deleteLater()'d — any lingering reference to it is a zombie.
        mm.MainWindow._rebuild_room_buttons(window, cats)

        # `_active_btn` must now point at the new Attic button, not the
        # destroyed old one.
        assert window._active_btn is not None
        assert window._active_btn is window._room_btns["Attic"]
        assert window._active_btn is not old_attic_btn

        # The new button must still be a live Qt object.
        if _shiboken_is_valid is not None:
            assert _shiboken_is_valid(window._active_btn)

        # It must remain checked so the sidebar visibly reflects state.
        assert window._active_btn.isChecked()

    def test_stale_room_btns_entries_dropped_when_room_empties(self, qt_app):
        window = _bare_window(qt_app)
        mm.MainWindow._rebuild_room_buttons(
            window,
            [_make_cat(1, "Attic"), _make_cat(2, "Floor1_Large")],
        )
        assert set(window._room_btns) == {"Attic", "Floor1_Large"}

        # Attic empties out (last cat moved downstairs). After rebuild the
        # dict must NOT retain a dangling pointer to the destroyed Attic
        # button.
        mm.MainWindow._rebuild_room_buttons(window, [_make_cat(2, "Floor1_Large")])
        assert set(window._room_btns) == {"Floor1_Large"}

    def test_active_btn_cleared_when_active_room_disappears(self, qt_app):
        window = _bare_window(qt_app)
        mm.MainWindow._rebuild_room_buttons(
            window,
            [_make_cat(1, "Attic"), _make_cat(2, "Floor1_Large")],
        )
        window._active_btn = window._room_btns["Attic"]

        # Active room empties — there is no replacement button to repoint
        # at, so `_active_btn` must end up as None rather than a dead
        # reference.
        mm.MainWindow._rebuild_room_buttons(window, [_make_cat(2, "Floor1_Large")])
        assert window._active_btn is None

    def test_rebuild_with_non_room_active_btn_leaves_it_untouched(self, qt_app):
        """If the user had a top-level button active (e.g., 'All Cats')
        rather than a room, `_rebuild_room_buttons` must not clobber it
        — those buttons live outside `_rooms_vb` and are never destroyed.
        """
        window = _bare_window(qt_app)
        top_level_btn = QPushButton("All Cats")
        top_level_btn.setCheckable(True)
        top_level_btn.setChecked(True)
        window._active_btn = top_level_btn

        mm.MainWindow._rebuild_room_buttons(
            window,
            [_make_cat(1, "Attic")],
        )

        assert window._active_btn is top_level_btn
        assert window._active_btn.isChecked()
