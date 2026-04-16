import os
import sys
import json
from pathlib import Path

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))

from mewgenics.utils.trait_ratings import TraitRatings


def test_fresh_trait_ratings(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    assert tr.active_profile == 1
    assert tr.ratings == {}
    assert len(tr.profiles) == 0  # no profiles until first save


def test_set_and_get_rating(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    tr.set_rating("Vurp", 1)
    assert tr.get_rating("Vurp") == 1
    tr.set_rating("Vurp", -1)
    assert tr.get_rating("Vurp") == -1
    tr.set_rating("Vurp", None)
    assert tr.get_rating("Vurp") is None


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    tr.set_rating("Vurp", 2)
    tr.set_rating("TankSwap", -1)
    tr.set_auto_weights({"stat_7": 10.0})
    tr.set_manual_weights({"stat_weight": 3})
    tr.save()

    tr2 = TraitRatings(path)
    assert tr2.get_rating("Vurp") == 2
    assert tr2.get_rating("TankSwap") == -1
    assert tr2.get_auto_weights()["stat_7"] == 10.0
    assert tr2.get_manual_weights()["stat_weight"] == 3


def test_profile_switch(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    tr.set_rating("Vurp", 2)
    tr.set_auto_weights({"stat_7": 10.0})

    # Switch to profile 2 — saves current to slot 1, loads empty slot 2
    tr.switch_profile(2)
    assert tr.active_profile == 2
    assert tr.get_rating("Vurp") is None  # slot 2 is empty
    assert tr.get_auto_weights() == {}

    # Set something in profile 2
    tr.set_rating("Vurp", -1)

    # Switch back to profile 1 — restores original state
    tr.switch_profile(1)
    assert tr.active_profile == 1
    assert tr.get_rating("Vurp") == 2
    assert tr.get_auto_weights()["stat_7"] == 10.0

    # Verify profile 2 persists
    tr.switch_profile(2)
    assert tr.get_rating("Vurp") == -1


def test_five_profiles(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    for i in range(1, 6):
        tr.switch_profile(i)
        tr.set_rating("test", i)
    # Verify each slot kept its value
    for i in range(1, 6):
        tr.switch_profile(i)
        assert tr.get_rating("test") == i


def test_missing_file_gives_defaults(tmp_path):
    path = str(tmp_path / "nonexistent.scoring.json")
    tr = TraitRatings(path)
    assert tr.active_profile == 1
    assert tr.ratings == {}


def test_auto_options_persistence(tmp_path):
    path = str(tmp_path / "test.scoring.json")
    tr = TraitRatings(path)
    tr.set_auto_options({"hide_kittens": True, "display_mode": "values"})
    tr.save()

    tr2 = TraitRatings(path)
    opts = tr2.get_auto_options()
    assert opts["hide_kittens"] is True
    assert opts["display_mode"] == "values"
