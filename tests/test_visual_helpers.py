import os
import sys
from pathlib import Path
from types import SimpleNamespace

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

import save_parser as sp
from save_parser import (
    _appearance_group_names,
    _appearance_preview_text,
    _mutation_stat_bonus_from_entries,
    _parse_mutation_stat_delta,
    _read_visual_mutation_entries,
    _visual_mutation_chip_items,
)


def test_visual_mutation_chip_items_merge_duplicate_slots(monkeypatch):
    monkeypatch.setattr(sp, "load_visual_mutation_names", lambda: {})
    monkeypatch.setattr(sp, "_VISUAL_MUT_DATA", {"legs": {401: ("Mutation 401", "Fast")}})

    table = [0] * 72
    table[18] = 401
    table[23] = 401

    entries = _read_visual_mutation_entries(table)
    chips = _visual_mutation_chip_items(entries)

    assert chips == [
        (
            "Leg Mutation Fast",
            "Leg Mutation (ID 401)\nLeg Mutation Fast\nAffects: Left Leg, Right Leg",
            False,
        )
    ]


def test_visual_mutation_chip_items_skip_base_part_ids(monkeypatch):
    """Base/default body part IDs (no gpak or catalog entry) must not appear as mutations.

    Real saves store every cat's base sprite selection in the same slots as
    mutations (low IDs like 23, 100, 189). Only entries with a lookup
    (gpak data or catalog fallback) or the "missing part" sentinel
    (0xFFFFFFFE) should surface as chips.
    """
    monkeypatch.setattr(sp, "load_visual_mutation_names", lambda: {})
    monkeypatch.setattr(sp, "_VISUAL_MUT_DATA", {"body": {305: ("Conjoined Bod", "+2 CON")}})

    table = [0] * 72
    table[0] = 23          # fur base (no lookup → skip)
    table[3] = 305         # body real mutation (gpak hit → keep)
    table[8] = 100         # head base (no lookup → skip)
    table[18] = 0xFFFF_FFFE  # leg missing-part sentinel (→ keep as defect)

    entries = _read_visual_mutation_entries(table)
    chips = _visual_mutation_chip_items(entries)

    texts = [chip[0] for chip in chips]
    assert "Conjoined Bod" in texts
    assert not any("Fur 23" in t or "Head 100" in t for t in texts)


def test_appearance_group_names_and_preview_text():
    cat = SimpleNamespace(
        visual_mutation_entries=[
            {"group_key": "fur", "name": "Tabby"},
            {"group_key": "fur", "name": "Spotted"},
            {"group_key": "tail", "name": "Long"},
        ]
    )

    assert _appearance_group_names(cat, "fur") == ["Tabby", "Spotted"]
    assert _appearance_group_names(cat, "body") == ["Base Body"]
    assert _appearance_group_names(cat, "tail") == ["Long"]
    assert _appearance_preview_text(["Tabby"], ["Tabby"]) == "Likely Tabby"
    assert _appearance_preview_text(["Tabby"], ["Spotted"]) == "Probabilistic: Tabby or Spotted"
    assert _appearance_preview_text([], []) == "No distinct appearance data"


def test_parse_mutation_stat_delta_parses_stat_bonuses_and_ignores_non_stats():
    assert _parse_mutation_stat_delta("+1 LCK") == {"LCK": 1}
    assert _parse_mutation_stat_delta("-1 SPD, +2 LCK") == {"SPD": -1, "LCK": 2}
    assert _parse_mutation_stat_delta("+2 CON, -1 DEX") == {"CON": 2, "DEX": -1}
    assert _parse_mutation_stat_delta("+2 Strength") == {"STR": 2}
    # Non-stat effects must not leak into the sum.
    assert _parse_mutation_stat_delta("+1 Range") == {}
    assert _parse_mutation_stat_delta("Gain a random stat up") == {}
    assert _parse_mutation_stat_delta("") == {}


def test_mutation_stat_bonus_merges_paired_body_parts():
    """A mutation applied to both arm slots via identical ids counts once."""
    entries = [
        {"group_key": "fur", "mutation_id": 302, "detail": "+1 LCK"},
        {"group_key": "body", "mutation_id": 410, "detail": "+2 CON, -1 SPD"},
        {"group_key": "arms", "mutation_id": 407, "detail": "+2 CON, -1 DEX"},
        {"group_key": "arms", "mutation_id": 407, "detail": "+2 CON, -1 DEX"},  # L+R duplicate
        {"group_key": "head", "mutation_id": 900, "detail": "+1 Range"},  # non-stat
    ]
    bonus = _mutation_stat_bonus_from_entries(entries)
    assert bonus["LCK"] == 1
    assert bonus["CON"] == 4  # body +2, arms +2 (merged, not doubled)
    assert bonus["SPD"] == -1
    assert bonus["DEX"] == -1
    assert bonus["STR"] == 0
    assert bonus["INT"] == 0
    assert bonus["CHA"] == 0


def test_mutation_stat_bonus_counts_asymmetric_pairs_separately():
    """Different mutation ids on L vs R are distinct mutations and both apply."""
    entries = [
        {"group_key": "arms", "mutation_id": 407, "detail": "+2 CON, -1 DEX"},
        {"group_key": "arms", "mutation_id": 432, "detail": "+2 LCK, -1 CHA"},
    ]
    bonus = _mutation_stat_bonus_from_entries(entries)
    assert bonus["CON"] == 2
    assert bonus["DEX"] == -1
    assert bonus["LCK"] == 2
    assert bonus["CHA"] == -1
