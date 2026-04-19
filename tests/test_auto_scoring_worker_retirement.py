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

from PySide6.QtWidgets import QApplication

import mewgenics.views.auto_scoring as auto_scoring_module


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


class _FakeSignal:
    def __init__(self):
        self.connected = []
        self.disconnected = []

    def connect(self, callback):
        self.connected.append(callback)

    def disconnect(self, callback):
        self.disconnected.append(callback)


class _OldWorker:
    def __init__(self):
        self.finished = _FakeSignal()
        self.interruption_requested = False
        self.deleted = False

    def requestInterruption(self):
        self.interruption_requested = True

    def deleteLater(self):
        self.deleted = True


class _NewWorker:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


def test_recompute_retires_previous_worker_before_starting_new_one(qt_app, monkeypatch):
    view = auto_scoring_module.AutoScoringView()
    view._alive = [SimpleNamespace(status="In House", room="Attic")]
    view._cats = list(view._alive)
    view._scope_cats = list(view._alive)
    view._scope_set = {id(view._alive[0])}

    old_worker = _OldWorker()
    view._scoring_worker = old_worker

    created_workers: list[_NewWorker] = []

    def _fake_worker(*args, **kwargs):
        worker = _NewWorker(*args, **kwargs)
        created_workers.append(worker)
        return worker

    monkeypatch.setattr(auto_scoring_module, "_ScoringWorker", _fake_worker)
    monkeypatch.setattr(view, "_read_options", lambda: None)
    monkeypatch.setattr(view, "_compute_scope", lambda: None)

    view._recompute()

    assert old_worker.interruption_requested is True
    assert old_worker.finished.disconnected == [view._on_scoring_done]
    assert old_worker.finished.connected == [old_worker.deleteLater]

    assert len(created_workers) == 1
    new_worker = created_workers[0]
    assert new_worker.started is True
    assert new_worker.finished.connected == [view._on_scoring_done]
    assert view._scoring_worker is new_worker
