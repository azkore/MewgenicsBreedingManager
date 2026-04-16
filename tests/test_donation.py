import os
import sys
from types import SimpleNamespace

_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(_proj_root, "src")
sys.path.insert(0, _src_dir)
sys.path.insert(0, _proj_root)

from mewgenics.utils.cat_analysis import _donation_candidate_base_reason, _is_donation_candidate


def _make_cat(*, disorders=None, base_stats=None, aggression=0.2, must_breed=False):
    return SimpleNamespace(
        disorders=list(disorders or []),
        base_stats=base_stats or {"STR": 3, "DEX": 3, "CON": 3, "INT": 3, "SPD": 3, "CHA": 3, "LCK": 3},
        aggression=aggression,
        must_breed=must_breed,
    )


def test_eternal_youth_cats_are_not_donation_candidates():
    cat = _make_cat(disorders=["EternalYouth"])

    assert _donation_candidate_base_reason(cat) is None
    assert not _is_donation_candidate(cat)


def test_non_eternal_youth_cats_still_can_be_donation_candidates():
    cat = _make_cat()

    assert _donation_candidate_base_reason(cat) is not None
    assert _is_donation_candidate(cat)
