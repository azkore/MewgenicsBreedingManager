import sys
from pathlib import Path
from types import SimpleNamespace

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))

from mewgenics.scoring.cat_stats import get_cat_stats, get_mutation_stat_bonuses


def _make_cat(**kwargs):
    defaults = {
        "base_stats": {"STR": 5, "DEX": 4, "CON": 6, "INT": 3, "SPD": 7, "CHA": 5, "LCK": 4},
        "total_stats": {"STR": 5, "DEX": 3, "CON": 6, "INT": 3, "SPD": 7, "CHA": 5, "LCK": 4},
        "visual_mutation_entries": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_get_cat_stats_base():
    cat = _make_cat()
    result = get_cat_stats(cat, use_current=False, add_mutation_stats=False)
    assert result == cat.base_stats


def test_get_cat_stats_current():
    cat = _make_cat()
    result = get_cat_stats(cat, use_current=True, add_mutation_stats=False)
    assert result == cat.total_stats


def test_get_cat_stats_current_fallback_to_base():
    cat = _make_cat(total_stats=None)
    result = get_cat_stats(cat, use_current=True, add_mutation_stats=False)
    assert result == cat.base_stats


def test_get_mutation_stat_bonuses_parses_detail():
    cat = _make_cat(visual_mutation_entries=[
        {"detail": "+2 CON, -1 DEX"},
        {"detail": "+1 LCK"},
        {"detail": ""},
        {"detail": "+1 Range"},  # non-stat, ignored
    ])
    bonuses = get_mutation_stat_bonuses(cat)
    assert bonuses == {"CON": 2, "DEX": -1, "LCK": 1}


def test_get_cat_stats_with_mutation_stats():
    cat = _make_cat(visual_mutation_entries=[
        {"detail": "+2 CON, -1 DEX"},
    ])
    result = get_cat_stats(cat, use_current=False, add_mutation_stats=True)
    assert result["CON"] == 8  # 6 + 2
    assert result["DEX"] == 3  # 4 - 1
    assert result["STR"] == 5  # unchanged


def test_get_mutation_stat_bonuses_empty():
    cat = _make_cat()
    bonuses = get_mutation_stat_bonuses(cat)
    assert bonuses == {}
