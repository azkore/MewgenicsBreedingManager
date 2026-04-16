"""
Regression tests for the displayed trait buckets used by the UI.
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QAbstractItemView, QHeaderView

from mewgenics.views.calibration import CalibrationView, _CALIBRATION_TRAIT_OPTIONS, _trait_label_from_value


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_aggression_and_libido_cutoffs():
    for field in ("aggression", "libido"):
        assert _trait_label_from_value(field, 0.29) == "low"
        assert _trait_label_from_value(field, 0.30) == "average"
        assert _trait_label_from_value(field, 0.70) == "average"
        assert _trait_label_from_value(field, 0.71) == "high"


def test_inbredness_extreme_tier():
    assert _trait_label_from_value("inbredness", 0.10) == "not"
    assert _trait_label_from_value("inbredness", 0.25) == "slightly"
    assert _trait_label_from_value("inbredness", 0.50) == "moderately"
    assert _trait_label_from_value("inbredness", 0.80) == "highly"
    assert _trait_label_from_value("inbredness", 0.8001) == "extremely"
    assert _trait_label_from_value("inbredness", "extreme") == "extremely"
    assert _CALIBRATION_TRAIT_OPTIONS["inbredness"][-1] == "extremely"
    assert CalibrationView._TRAIT_SORT["extremely"] > CalibrationView._TRAIT_SORT["highly"]


def test_calibration_selection_is_contiguous(qt_app):
    view = CalibrationView()
    assert view._table.selectionBehavior() == QAbstractItemView.SelectRows
    assert view._table.selectionMode() == QAbstractItemView.ExtendedSelection
    assert view._table.horizontalHeader().sectionResizeMode(view.COL_NAME) == QHeaderView.Interactive
    assert view._table.horizontalHeader().sectionResizeMode(view.COL_STATUS) == QHeaderView.Interactive
    assert view._table.columnWidth(view.COL_NAME) >= 140
    assert view._table.columnWidth(view.COL_STATUS) >= 92
