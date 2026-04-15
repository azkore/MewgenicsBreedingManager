# Automatic Scoring View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scope-aware individual cat scoring view ("Automatic Scoring") with shared trait ratings, 5-slot profiles, heatmap visualization, and filters — integrated as a new sidebar section alongside the existing Manual Scoring view.

**Architecture:** Pure-Python scoring engine in `src/mewgenics/scoring/` (ported from byronaltice fork). Shared trait ratings + profiles in `utils/trait_ratings.py`. Qt view in `views/auto_scoring.py` following existing view patterns. Manual Scoring migrated to shared persistence.

**Tech Stack:** Python 3.11+, PySide6, pytest

**Spec:** `docs/superpowers/specs/2026-04-15-automatic-scoring-design.md`

**Byron source reference:** `byronaltice/main` branch — `src/breed_priority/scoring.py`, `src/breed_priority/recompute_helpers.py`, `src/breed_priority/stats_overview.py`, `src/breed_priority/filters.py`, `src/breed_priority/__init__.py`

---

## File Map

**Create:**
- `src/mewgenics/scoring/__init__.py` — Package init, re-exports
- `src/mewgenics/scoring/engine.py` — Scoring function, weights, tiers, ScoreResult
- `src/mewgenics/scoring/helpers.py` — Relationship maps, seven-sets, compute_all_scores, heatmap norms
- `src/mewgenics/scoring/cat_stats.py` — get_cat_stats, get_mutation_stat_bonuses
- `src/mewgenics/scoring/filters.py` — FilterState data class, cat_passes_filter
- `src/mewgenics/utils/trait_ratings.py` — TraitRatings class, profile management, JSON persistence
- `src/mewgenics/views/auto_scoring.py` — AutoScoringView widget
- `tests/test_scoring_engine.py` — Scoring engine tests
- `tests/test_trait_ratings.py` — Shared ratings + profile tests

**Modify:**
- `src/mewgenics/utils/paths.py` — Add `_scoring_path()` sidecar helper
- `src/mewgenics/views/manual_scoring.py` — Profile dropdown, migrate persistence to shared TraitRatings
- `src/mewgenics/main_window.py` — Sidebar section, view wiring, shared TraitRatings instance
- `src/mewgenics/dialogs.py` — Add StatsOverviewDialog

---

## Task 1: Scoring Engine — `cat_stats.py`

**Files:**
- Create: `src/mewgenics/scoring/__init__.py`
- Create: `src/mewgenics/scoring/cat_stats.py`
- Create: `tests/test_scoring_engine.py`

- [ ] **Step 1: Create scoring package with `__init__.py`**

```python
# src/mewgenics/scoring/__init__.py
"""Automatic scoring engine — pure Python, no Qt dependencies."""
```

- [ ] **Step 2: Write failing tests for `get_cat_stats` and `get_mutation_stat_bonuses`**

```python
# tests/test_scoring_engine.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mewgenics.scoring.cat_stats'`

- [ ] **Step 4: Implement `cat_stats.py`**

Port from Byron's `src/breed_priority/stats_overview.py::get_cat_stats` and `get_mutation_stat_bonuses`. This is pure logic — no Qt.

```python
# src/mewgenics/scoring/cat_stats.py
"""Stat resolution for scoring — base, total, or total+mutation modes."""

import re

_MUT_STAT_RE = re.compile(r'([+-]?\d+)\s+(STR|CON|INT|DEX|SPD|LCK|CHA)')


def get_mutation_stat_bonuses(cat) -> dict[str, int]:
    """Return {stat_name: total_delta} from visual mutation detail fields."""
    bonuses: dict[str, int] = {}
    for entry in getattr(cat, 'visual_mutation_entries', []) or []:
        detail = entry.get('detail', '') or ''
        for match in _MUT_STAT_RE.finditer(detail):
            delta = int(match.group(1))
            stat = match.group(2)
            bonuses[stat] = bonuses.get(stat, 0) + delta
    return bonuses


def get_cat_stats(cat, use_current: bool, add_mutation_stats: bool = False) -> dict[str, int]:
    """Return the stat dict to use for scoring.

    use_current=True  -> total_stats (base + modifiers/injuries)
    use_current=False -> base_stats
    add_mutation_stats -> parse mutation detail fields and add on top
    """
    if use_current:
        source = getattr(cat, 'total_stats', None) or getattr(cat, 'base_stats', {}) or {}
    else:
        source = getattr(cat, 'base_stats', {}) or {}

    if not add_mutation_stats:
        return source

    bonuses = get_mutation_stat_bonuses(cat)
    if not bonuses:
        return source
    result = dict(source)
    for stat, delta in bonuses.items():
        if stat in result:
            result[stat] = result[stat] + delta
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/mewgenics/scoring/__init__.py src/mewgenics/scoring/cat_stats.py tests/test_scoring_engine.py
git commit -m "feat(scoring): add cat_stats module with stat resolution and mutation bonuses"
```

---

## Task 2: Scoring Engine — `engine.py` (core function)

**Files:**
- Create: `src/mewgenics/scoring/engine.py`
- Modify: `tests/test_scoring_engine.py`

- [ ] **Step 1: Write failing tests for the scoring engine**

Append to `tests/test_scoring_engine.py`:

```python
from mewgenics.scoring.engine import (
    compute_breed_priority_score, ScoreResult, priority_tier,
    BREED_PRIORITY_WEIGHTS, ability_base, is_basic_trait,
)


def test_priority_tier_boundaries():
    assert priority_tier(10.0) == ("Keep", "#f0c060")
    assert priority_tier(4.0) == ("Good", "#1ec8a0")
    assert priority_tier(0.0) == ("Neutral", "#777777")
    assert priority_tier(-1.0) == ("Consider", "#e08030")
    assert priority_tier(-5.0) == ("Consider", "#e08030")
    assert priority_tier(-6.0) == ("Cull", "#e04040")


def test_ability_base_strips_tier2():
    assert ability_base("Vurp2") == "Vurp"
    assert ability_base("Vurp") == "Vurp"
    assert ability_base("A2") == "A"
    assert ability_base("2") == "2"  # single char, no strip


def test_is_basic_trait():
    assert is_basic_trait("BasicAttack") is True
    assert is_basic_trait("basicmove") is True
    assert is_basic_trait("Vurp") is False


def _scope_cat(name, stats=None, gender="M", room="Floor1_Large",
               abilities=None, passive_abilities=None, mutations=None,
               defects=None, disorders=None, aggression=0.5, libido=0.5,
               sexuality="straight", age=5, lovers=None, haters=None,
               children=None, status="In House"):
    s = stats or {"STR": 5, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5}
    return SimpleNamespace(
        name=name, base_stats=dict(s), total_stats=dict(s),
        gender=gender, room=room, status=status, age=age,
        abilities=abilities or [], passive_abilities=passive_abilities or [],
        mutations=mutations or [], defects=defects or [], disorders=disorders or [],
        aggression=aggression, libido=libido, sexuality=sexuality,
        lovers=lovers or [], haters=haters or [], children=children or [],
        visual_mutation_entries=[], db_key=id(name),
    )


def test_score_basic_cat_no_scope():
    """A cat scored alone with default weights — stat sum is the main contributor."""
    cat = _scope_cat("Solo", stats={"STR": 7, "DEX": 7, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    result = compute_breed_priority_score(
        cat, scope_cats=[], ma_ratings={},
        stat_names=["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"],
    )
    assert isinstance(result, ScoreResult)
    assert result.total == 0.0  # no scope = no percentile, no 7-rarity
    assert result.tier == "Neutral"


def test_score_7_rarity_sole_owner():
    """Sole owner of a 7 in a stat gets 2x weight."""
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat_a = _scope_cat("A", stats={"STR": 7, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    cat_b = _scope_cat("B", stats={"STR": 5, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    scope = [cat_a, cat_b]
    result = compute_breed_priority_score(
        cat_a, scope_cats=scope, ma_ratings={}, stat_names=stat_names,
    )
    # Sole owner: stat_7 * 2 = 5.0 * 2 = 10.0, plus 7-count: 2.0 * 1 = 2.0
    assert result.subtotals["stat_7"] == 10.0
    assert result.subtotals["stat_7_count"] == 2.0


def test_score_7_rarity_shared():
    """When two cats share a 7 in STR, the bonus is the base weight (not 2x)."""
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat_a = _scope_cat("A", stats={"STR": 7, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    cat_b = _scope_cat("B", stats={"STR": 7, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    scope = [cat_a, cat_b]
    result = compute_breed_priority_score(
        cat_a, scope_cats=scope, ma_ratings={}, stat_names=stat_names,
    )
    assert result.subtotals["stat_7"] == 5.0  # base weight, 2 cats < threshold 7


def test_score_trait_rating_desirable():
    """A desirable trait on a sole owner gets 2x weight."""
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat = _scope_cat("A", abilities=["Vurp"])
    scope = [cat]
    result = compute_breed_priority_score(
        cat, scope_cats=scope, ma_ratings={"Vurp": 1},
        stat_names=stat_names,
    )
    # Sole owner of desirable: 2 * trait_desirable(2.0) = 4.0
    assert result.subtotals["trait_desirable"] == 4.0


def test_score_gene_risk_safe():
    """Cat with zero risk against all scope partners gets zero_risk_bonus."""
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat_a = _scope_cat("A", gender="M")
    cat_b = _scope_cat("B", gender="F")
    scope = [cat_a, cat_b]

    def fake_risk(a, b, memo=None):
        return 0.0

    def fake_can_breed(a, b):
        return (True, [])

    result = compute_breed_priority_score(
        cat_a, scope_cats=scope, ma_ratings={}, stat_names=stat_names,
        gene_risk_lookup=fake_risk, can_breed_fn=fake_can_breed,
    )
    assert result.subtotals["zero_risk_bonus"] == 2.0


def test_score_aggression_low():
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat = _scope_cat("Calm", aggression=0.1)
    result = compute_breed_priority_score(cat, [], {}, stat_names)
    assert result.subtotals["low_aggression"] == 1.0


def test_score_age_penalty():
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat = _scope_cat("Old", age=14)
    result = compute_breed_priority_score(cat, [], {}, stat_names)
    # age 14, threshold 10, over=4, mult=1+(4-1)//3=2, pts=2*-2.0=-4.0
    assert result.subtotals["age_penalty"] == -4.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mewgenics.scoring.engine'`

- [ ] **Step 3: Implement `engine.py`**

Port from Byron's `src/breed_priority/scoring.py`. The core algorithm is preserved with type hints added and a `can_breed_fn` parameter added (instead of importing `can_breed` at module level) for testability.

```python
# src/mewgenics/scoring/engine.py
"""Automatic scoring — weights, tiers, and main scoring function.

Pure Python — no Qt dependencies. Ported from byronaltice's breed_priority/scoring.py.
"""

from __future__ import annotations

from save_parser import risk_percent, can_breed

from mewgenics.scoring.cat_stats import get_cat_stats

# ── Trait thresholds ─────────────────────────────────────────────────────────

TRAIT_LOW_THRESHOLD = 0.3
TRAIT_HIGH_THRESHOLD = 0.7
GENETIC_SAFE_RISK_FLOOR = 2.0

# ── Default weights ──────────────────────────────────────────────────────────

BREED_PRIORITY_WEIGHTS: dict[str, float] = {
    "stat_7":           5.0,
    "stat_7_threshold": 7.0,
    "stat_7_count":     2.0,
    "trait_top_priority": 2.0,
    "trait_desirable":   2.0,
    "trait_undesirable": -2.0,
    "low_aggression":  1.0,
    "unknown_gender":  1.0,
    "high_libido":     0.5,
    "high_aggression": -1.0,
    "low_libido":      -0.5,
    "gay_pref":        0.0,
    "bi_pref":         0.0,
    "no_children":           -2.0,
    "zero_risk_bonus":        2.0,
    "gene_risk_threshold":    2.0,
    "gene_risk_penalty_scale": 10.0,
    "stat_sum":        4.0,
    "age_penalty":    -2.0,
    "age_threshold":  10.0,
    "love_interest":      1.0,
    "rivalry":           -2.0,
    "love_interest_room": 0.0,
    "rivalry_room":       0.0,
    "seven_sub":           0.0,
    "seven_sub_threshold": 1.0,
    "cha_low":             0.0,
}

# ── Weight editor UI rows ────────────────────────────────────────────────────

WEIGHT_UI_ROWS: list[tuple[str | None, str | tuple | None]] = [
    ("stat_sum",         "Stat Sum"),
    (None, None),
    ("age_penalty",      "Age penalty"),
    ("age_threshold",    "  \u2514 threshold"),
    (None, None),
    ("stat_7",           "7rare"),
    ("stat_7_threshold", "  \u2514 threshold"),
    ("stat_7_count",     "7-count"),
    (None, None),
    ("seven_sub",          "7-Sub score"),
    ("seven_sub_threshold","  \u2514 threshold"),
    (None, None),
    ("cha_low",            "CHA \u2264 4 penalty"),
    (None, None),
    ("gay_pref",         ("Sex", "Gay")),
    ("bi_pref",          ("",       "Bi")),
    (None, None),
    ("high_libido",      ("Lib", "High")),
    ("low_libido",       ("",       "Low")),
    (None, None),
    ("unknown_gender",   "Unknown gender"),
    (None, None),
    ("no_children",             "Genetic Safety Risk"),
    ("zero_risk_bonus",         "Genetic Safety Bonus"),
    ("gene_risk_threshold",     "  \u2514 threshold (%)"),
    ("gene_risk_penalty_scale", "  \u2514 penalty scale"),
    (None, None),
    ("high_aggression",  ("Aggro", "High")),
    ("low_aggression",   ("",      "Low")),
    (None, None),
    ("rivalry",            ("Hate", "In Scope")),
    ("rivalry_room",       ("",     "In Room")),
    (None, None),
    ("love_interest",      ("Love", "In Scope")),
    ("love_interest_room", ("",     "In Room")),
    (None, None),
    ("trait_top_priority", ("Trait", "Top Priority")),
    ("trait_desirable",    ("",      "Desirable")),
    ("trait_undesirable",  ("",      "Undesirable")),
]

# ── Score table columns ──────────────────────────────────────────────────────

SCORE_COLUMNS: list[tuple[str, list[str]]] = [
    ("Sum",   ["stat_sum"]),
    ("Age",   ["age_penalty"]),
    ("7rare", ["stat_7"]),
    ("7cnt",  ["stat_7_count"]),
    ("7sub",  ["seven_sub"]),
    ("CHA",   ["cha_low"]),
    ("Sex",   ["gay_pref", "bi_pref"]),
    ("Lib",   ["high_libido", "low_libido"]),
    ("Gender", ["unknown_gender"]),
    ("Gene",  ["no_children", "zero_risk_bonus"]),
    ("Aggro", ["low_aggression", "high_aggression"]),
    ("\U0001f4a5\U0001f52d",    ["rivalry"]),
    ("\U0001f4a5\U0001f3e0",    ["rivalry_room"]),
    ("\U0001f497\U0001f52d",    ["love_interest"]),
    ("\U0001f497\U0001f3e0",    ["love_interest_room"]),
    ("Trait", ["trait_top_priority", "trait_desirable", "trait_undesirable"]),
]

# ── Tier classification ──────────────────────────────────────────────────────

BREED_PRIORITY_TIERS: list[tuple[float | None, str, str]] = [
    (10,   "Keep",     "#f0c060"),
    ( 4,   "Good",     "#1ec8a0"),
    ( 0,   "Neutral",  "#777777"),
    (-5,   "Consider", "#e08030"),
    (None, "Cull",     "#e04040"),
]

# ── Trait rating values ──────────────────────────────────────────────────────

TRAIT_RATING_OPTIONS: list[tuple[str, int | None]] = [
    ("Top Priority", 2),
    ("Desirable", 1),
    ("Neutral", 0),
    ("Undecided", None),
    ("Undesirable", -1),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

class ScoreResult:
    __slots__ = ("total", "tier", "tier_color", "breakdown", "subtotals",
                 "scope_gene_risk")

    def __init__(self, total: float, tier: str, tier_color: str,
                 breakdown: list[tuple[str, float]],
                 subtotals: dict[str, float] | None = None,
                 scope_gene_risk: float | None = None):
        self.total = total
        self.tier = tier
        self.tier_color = tier_color
        self.breakdown = breakdown
        self.subtotals = subtotals or {}
        self.scope_gene_risk = scope_gene_risk


def priority_tier(score: float) -> tuple[str, str]:
    for threshold, label, color in BREED_PRIORITY_TIERS:
        if threshold is None or score >= threshold:
            return label, color
    return "Cull", "#e04040"


def is_basic_trait(name: str) -> bool:
    return name.lower().startswith("basic")


def ability_base(name: str) -> str:
    if len(name) > 1 and name[-1] == "2":
        return name[:-1]
    return name


# ── Main scoring function ────────────────────────────────────────────────────

def compute_breed_priority_score(
    cat,
    scope_cats: list,
    ma_ratings: dict[str, int | None],
    stat_names: list[str],
    weights: dict[str, float] | None = None,
    mutation_display_name=None,
    scope_stat_sums: list[float] | None = None,
    hated_by: list | None = None,
    gene_risk_lookup=None,
    gene_risk_cache: dict | None = None,
    use_current_stats: bool = False,
    add_mutation_stats: bool = False,
    can_breed_fn=None,
) -> ScoreResult:
    """Compute breed priority score for an individual cat.

    Args:
        cat: The cat to score.
        scope_cats: All cats in the selected scope.
        ma_ratings: {trait_key: rating} where 2=Top, 1=Desirable, 0=Neutral,
            None=Undecided, -1=Undesirable.
        stat_names: Ordered stat keys, e.g. ["STR", "DEX", ...].
        weights: Override weight dict. Defaults to BREED_PRIORITY_WEIGHTS.
        mutation_display_name: Callable(str) -> str for display labels.
        scope_stat_sums: Pre-sorted list of stat sums for percentile calc.
        hated_by: Cats in scope that hate this cat (reverse lookup).
        gene_risk_lookup: Callable(cat, cat) -> float. Defaults to risk_percent.
        gene_risk_cache: Mutable dict for caching pair risk values.
        use_current_stats: Use total_stats instead of base_stats.
        add_mutation_stats: Add mutation stat bonuses on top.
        can_breed_fn: Callable(cat, cat) -> (bool, list). Defaults to can_breed.
    """
    _w = weights if weights is not None else BREED_PRIORITY_WEIGHTS
    _display = mutation_display_name or (lambda n: n)
    _can_breed = can_breed_fn or can_breed
    _cat_stats = get_cat_stats(cat, use_current_stats, add_mutation_stats)
    _scope_stats = {id(c): get_cat_stats(c, use_current_stats, add_mutation_stats)
                    for c in scope_cats}
    breakdown: list[tuple[str, float]] = []
    subtotals: dict[str, float] = {}
    for key in BREED_PRIORITY_WEIGHTS:
        subtotals[key] = 0.0
    scope_set = {id(c) for c in scope_cats}
    _cat_in_scope = id(cat) in scope_set

    # ── Unknown gender bonus ──────────────────────────────────────────────
    if cat.gender == "?":
        breakdown.append(("Unknown gender (?)", _w["unknown_gender"]))
        subtotals["unknown_gender"] = _w["unknown_gender"]

    # ── CHA penalty ───────────────────────────────────────────────────────
    w_cha = _w.get("cha_low", 0.0)
    if w_cha != 0.0:
        _cha = _cat_stats.get("CHA")
        if _cha == 4:
            breakdown.append(("CHA = 4", round(w_cha, 3)))
            subtotals["cha_low"] = round(w_cha, 3)
        elif _cha is not None and _cha <= 3:
            _cha_pts = round(w_cha * 2, 3)
            breakdown.append((f"CHA = {_cha} (2\u00d7)", _cha_pts))
            subtotals["cha_low"] = _cha_pts

    # ── Aggression / libido / sexuality ───────────────────────────────────
    if cat.aggression is not None and cat.aggression < TRAIT_LOW_THRESHOLD:
        breakdown.append(("Low aggression", _w["low_aggression"]))
        subtotals["low_aggression"] = _w["low_aggression"]

    if cat.libido is not None and cat.libido >= TRAIT_HIGH_THRESHOLD:
        breakdown.append(("High libido", _w["high_libido"]))
        subtotals["high_libido"] = _w["high_libido"]

    _sex = getattr(cat, 'sexuality', 'straight') or 'straight'
    if _sex == 'gay' and _w.get("gay_pref", 0.0) != 0.0:
        breakdown.append(("Gay", _w["gay_pref"]))
        subtotals["gay_pref"] = _w["gay_pref"]
    elif _sex == 'bi' and _w.get("bi_pref", 0.0) != 0.0:
        breakdown.append(("Bi", _w["bi_pref"]))
        subtotals["bi_pref"] = _w["bi_pref"]

    # ── Stat 7 rarity ─────────────────────────────────────────────────────
    _TARGET_N = int(round(_w.get("stat_7_threshold", 7.0)))
    _STAT7_BASE = _w["stat_7"]
    for stat_name in stat_names:
        if _cat_stats.get(stat_name) == 7:
            n_scope = sum(1 for c in scope_cats
                         if _scope_stats[id(c)].get(stat_name) == 7)
            n = n_scope if _cat_in_scope else n_scope + 1
            if n == 1:
                w = _w["stat_7"] * 2
                label = f"7 in {stat_name} (sole \u2605\u2605)"
            elif n <= _TARGET_N:
                w = _w["stat_7"]
                label = f"7 in {stat_name} ({n} in scope)"
            else:
                w = round(_STAT7_BASE * _TARGET_N / n, 3)
                label = f"7 in {stat_name} ({n} in scope, \u00f7{n / _TARGET_N:.1f})"
            breakdown.append((label, float(w)))
            subtotals["stat_7"] += float(w)

    # ── 7-count bonus ─────────────────────────────────────────────────────
    _w_7ct = _w.get("stat_7_count", 0.0)
    if _w_7ct != 0.0:
        _n_sevens = sum(1 for sn in stat_names if _cat_stats.get(sn) == 7)
        if _n_sevens > 0:
            _7ct_pts = round(_w_7ct * _n_sevens, 3)
            breakdown.append((f"{_n_sevens} stat{'s' if _n_sevens != 1 else ''} at 7", _7ct_pts))
            subtotals["stat_7_count"] = _7ct_pts

    # ── Trait scoring ─────────────────────────────────────────────────────
    scope_base_traits: dict[int, set[str]] = {
        id(c): (
            {ability_base(a) for a in
             list(c.abilities) + list(c.passive_abilities) + list(getattr(c, 'disorders', []))}
            | set(c.mutations)
            | set(getattr(c, 'defects', []))
        )
        for c in scope_cats
    }
    _w_top = _w.get("trait_top_priority", 0.0)
    _w_des = _w.get("trait_desirable", 0.0)
    _w_und = _w.get("trait_undesirable", 0.0)

    def _score_trait(label: str, rating: int | None, n: int):
        if rating is None or rating == 0:
            return
        if n == 1:
            if rating == 2:
                pts = 2 * _w_top
                tag = "Sole owner (top priority)"
            elif rating == 1:
                pts = 2 * _w_des
                tag = "Sole owner (desirable)"
            else:
                pts = _w_und
                tag = "Sole owner (undesirable)"
        elif rating == 2:
            pts = round(_w_top / n, 3)
            tag = f"Top Priority (\u00f7{n})"
        elif rating == 1:
            pts = round(_w_des / n, 3)
            tag = f"Desirable (\u00f7{n})"
        elif rating == -1:
            pts = _w_und
            tag = "Undesirable"
        else:
            return
        breakdown.append((f"{tag}: {label}", pts))
        if rating == 2:
            subtotals["trait_top_priority"] += pts
        elif rating == 1:
            subtotals["trait_desirable"] += pts
        elif rating == -1:
            subtotals["trait_undesirable"] += pts

    all_ability_bases = list({
        ability_base(m) for m in
        list(cat.abilities) + list(cat.passive_abilities) + list(getattr(cat, 'disorders', []))
        if not is_basic_trait(m)
    })
    for ma in all_ability_bases:
        rating = ma_ratings.get(ma)
        n_scope = sum(1 for c in scope_cats if ma in scope_base_traits[id(c)])
        n = max(1, n_scope if _cat_in_scope else n_scope + 1)
        _score_trait(_display(ma), rating, n)

    for ma in cat.mutations:
        if is_basic_trait(ma):
            continue
        rating = ma_ratings.get(ma)
        n_scope = sum(1 for c in scope_cats if ma in scope_base_traits[id(c)])
        n = max(1, n_scope if _cat_in_scope else n_scope + 1)
        _score_trait(ma, rating, n)

    for ma in getattr(cat, 'defects', []):
        if is_basic_trait(ma):
            continue
        rating = ma_ratings.get(ma)
        n_scope = sum(1 for c in scope_cats if ma in scope_base_traits[id(c)])
        n = max(1, n_scope if _cat_in_scope else n_scope + 1)
        _score_trait(ma, rating, n)

    # ── High aggression / low libido ──────────────────────────────────────
    if cat.aggression is not None and cat.aggression >= TRAIT_HIGH_THRESHOLD:
        breakdown.append(("High aggression", _w["high_aggression"]))
        subtotals["high_aggression"] = _w["high_aggression"]

    if cat.libido is not None and cat.libido < TRAIT_LOW_THRESHOLD:
        breakdown.append(("Low libido", _w["low_libido"]))
        subtotals["low_libido"] = _w["low_libido"]

    # ── Genetic safety ────────────────────────────────────────────────────
    risk_fn = gene_risk_lookup if callable(gene_risk_lookup) else risk_percent
    _risk_vals: list[float] = []
    for partner in scope_cats:
        if partner is cat:
            continue
        if not _can_breed(cat, partner)[0]:
            continue
        if gene_risk_cache is not None:
            _rk = (id(cat), id(partner)) if id(cat) < id(partner) else (id(partner), id(cat))
            _rv = gene_risk_cache.get(_rk)
            if _rv is None:
                _rv = float(risk_fn(cat, partner))
                gene_risk_cache[_rk] = _rv
        else:
            _rv = float(risk_fn(cat, partner))
        _risk_vals.append(_rv)

    gene_risk: float | None = (sum(_risk_vals) / len(_risk_vals)) if _risk_vals else None
    if gene_risk is not None:
        _gene_risk_display = float(int(round(gene_risk)))
        _gene_threshold = float(_w.get("gene_risk_threshold", GENETIC_SAFE_RISK_FLOOR))
        _gene_penalty_scale = float(_w.get("gene_risk_penalty_scale", 10.0))
        _effective_gene_risk = max(0.0, _gene_risk_display - _gene_threshold)
        gene_units = round(_effective_gene_risk * _gene_penalty_scale / 100.0, 3)
        if gene_units > 0:
            gene_pts = round(_w["no_children"] * gene_units, 3)
            breakdown.append((f"Genetic risk {gene_risk:.1f}% (R{int(_gene_risk_display)}, {_gene_threshold:.0f}% threshold)", gene_pts))
            subtotals["no_children"] = gene_pts
        elif _gene_risk_display <= _gene_threshold:
            safe_pts = float(_w.get("zero_risk_bonus", 0.0))
            if safe_pts != 0.0:
                breakdown.append((f"Genetic safety (R{int(_gene_risk_display)} \u2264 {_gene_threshold:.0f})", safe_pts))
                subtotals["zero_risk_bonus"] = safe_pts

    # ── Stat sum percentile ───────────────────────────────────────────────
    w_sum = _w.get("stat_sum", 0.0)
    if w_sum != 0 and scope_stat_sums:
        cat_sum = sum(_cat_stats.values())
        n_sums = len(scope_stat_sums)
        rank = sum(1 for v in scope_stat_sums if v <= cat_sum)
        pct = rank / n_sums * 100
        if pct >= 90:
            pts = w_sum
        elif pct >= 75:
            pts = max(0.0, w_sum - 1)
        elif pct >= 50:
            pts = max(0.0, w_sum - 2)
        else:
            pts = 0.0
        if pts:
            breakdown.append((f"Stat sum {cat_sum} ({pct:.0f}th percentile)", pts))
            subtotals["stat_sum"] = pts

    # ── Age penalty ───────────────────────────────────────────────────────
    w_age = _w.get("age_penalty", 0.0)
    if w_age != 0.0:
        age = getattr(cat, 'age', None)
        if age is not None:
            _age_thr = int(round(_w.get("age_threshold", 10.0)))
            if age > _age_thr:
                _over = age - _age_thr
                _mult = 1 + (_over - 1) // 3
                pts = round(_mult * w_age, 2)
                breakdown.append((f"Age {age} (+{_over} over threshold, {_mult}\u00d7)", pts))
                subtotals["age_penalty"] = pts

    # ── Love interest ─────────────────────────────────────────────────────
    w_love = _w.get("love_interest", 0.0)
    if w_love != 0.0:
        for lover in getattr(cat, 'lovers', []):
            if id(lover) in scope_set:
                pts = round(w_love, 2)
                breakdown.append((f"Loves {lover.name} (in scope)", pts))
                subtotals["love_interest"] = pts
                break

    # ── Rivalry ────────────────────────────────────────────────────────────
    w_rival = _w.get("rivalry", 0.0)
    if w_rival != 0.0:
        _rival_total = 0.0
        for hater in getattr(cat, 'haters', []):
            if id(hater) in scope_set:
                pts = round(w_rival, 2)
                breakdown.append((f"Hates {hater.name} (in scope)", pts))
                _rival_total += pts
        for hater in (hated_by or []):
            if id(hater) in scope_set and hater not in getattr(cat, 'haters', []):
                pts = round(w_rival, 2)
                breakdown.append((f"Hated by {hater.name} (in scope)", pts))
                _rival_total += pts
        if _rival_total:
            subtotals["rivalry"] = _rival_total

    # ── Love interest (room) ──────────────────────────────────────────────
    w_love_room = _w.get("love_interest_room", 0.0)
    if w_love_room != 0.0:
        _cat_room = getattr(cat, 'room', None)
        if _cat_room:
            for lover in getattr(cat, 'lovers', []):
                if getattr(lover, 'room', None) == _cat_room:
                    pts = round(w_love_room, 2)
                    breakdown.append((f"Loves {lover.name} (in room)", pts))
                    subtotals["love_interest_room"] = pts
                    break

    # ── Rivalry (room) ────────────────────────────────────────────────────
    w_rival_room = _w.get("rivalry_room", 0.0)
    if w_rival_room != 0.0:
        _cat_room = getattr(cat, 'room', None)
        if _cat_room:
            _rr_total = 0.0
            for hater in getattr(cat, 'haters', []):
                if getattr(hater, 'room', None) == _cat_room:
                    pts = round(w_rival_room, 2)
                    breakdown.append((f"Hates {hater.name} (in room)", pts))
                    _rr_total += pts
            for hater in (hated_by or []):
                if hater not in getattr(cat, 'haters', []) and getattr(hater, 'room', None) == _cat_room:
                    pts = round(w_rival_room, 2)
                    breakdown.append((f"Hated by {hater.name} (in room)", pts))
                    _rr_total += pts
            if _rr_total:
                subtotals["rivalry_room"] = _rr_total

    total = sum(pts for _, pts in breakdown)
    tier, color = priority_tier(total)
    return ScoreResult(total=total, tier=tier, tier_color=color,
                       breakdown=breakdown, subtotals=subtotals,
                       scope_gene_risk=gene_risk)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mewgenics/scoring/engine.py tests/test_scoring_engine.py
git commit -m "feat(scoring): add engine with breed priority scoring function"
```

---

## Task 3: Scoring Engine — `helpers.py`

**Files:**
- Create: `src/mewgenics/scoring/helpers.py`
- Modify: `tests/test_scoring_engine.py`

- [ ] **Step 1: Write failing tests for helpers**

Append to `tests/test_scoring_engine.py`:

```python
from mewgenics.scoring.helpers import (
    build_relationship_maps, compute_seven_sets,
    compute_all_scores, compute_heatmap_norms,
)


def test_build_relationship_maps():
    cat_a = _scope_cat("A")
    cat_b = _scope_cat("B", haters=[cat_a])
    cat_c = _scope_cat("C", lovers=[cat_a])
    hated_by, loved_by = build_relationship_maps([cat_a, cat_b, cat_c])
    assert cat_a in hated_by.get(id(cat_a), [])  # cat_b hates cat_a
    assert cat_c in loved_by.get(id(cat_a), [])   # cat_c loves cat_a


def test_compute_seven_sets():
    stat_names = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]
    cat_a = _scope_cat("A", stats={"STR": 7, "DEX": 7, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    cat_b = _scope_cat("B", stats={"STR": 7, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    scope_set = {id(cat_a), id(cat_b)}
    seven_sets, scope_7_sets = compute_seven_sets(
        [cat_a, cat_b], scope_set, stat_names=stat_names,
    )
    assert seven_sets[id(cat_a)] == frozenset({"STR", "DEX"})
    assert seven_sets[id(cat_b)] == frozenset({"STR"})
    assert len(scope_7_sets) == 2


def test_compute_heatmap_norms_disabled():
    col_max, row_max, score_max = compute_heatmap_norms({}, [], False, "column")
    assert col_max == {}
    assert row_max == {}
    assert score_max == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring_engine.py::test_build_relationship_maps -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `helpers.py`**

Port from Byron's `src/breed_priority/recompute_helpers.py`. Add `stat_names` parameter to `compute_seven_sets` instead of importing from `columns.py`.

```python
# src/mewgenics/scoring/helpers.py
"""Pre-computation helpers for automatic scoring.

Called once per recompute cycle. Pure Python — no Qt dependencies.
Ported from byronaltice's breed_priority/recompute_helpers.py.
"""

from __future__ import annotations

from save_parser import STAT_NAMES

from mewgenics.scoring.cat_stats import get_cat_stats
from mewgenics.scoring.engine import (
    SCORE_COLUMNS, ScoreResult,
    compute_breed_priority_score,
)


def build_relationship_maps(cats: list) -> tuple[dict[int, list], dict[int, list]]:
    """Build reverse hated-by and loved-by maps from all in-house cats.

    Returns (hated_by_map, loved_by_map) keyed by id(target_cat).
    """
    all_in_house = [c for c in cats if c.status == "In House"]
    hated_by_map: dict[int, list] = {}
    for c in all_in_house:
        for h in getattr(c, 'haters', []):
            hated_by_map.setdefault(id(h), []).append(c)
    loved_by_map: dict[int, list] = {}
    for c in all_in_house:
        for lv in getattr(c, 'lovers', []):
            loved_by_map.setdefault(id(lv), []).append(c)
    return hated_by_map, loved_by_map


def compute_seven_sets(
    alive: list,
    scope_set: set[int],
    use_current_stats: bool = False,
    add_mutation_stats: bool = False,
    stat_names: list[str] | None = None,
) -> tuple[dict[int, frozenset], dict[int, frozenset]]:
    """Pre-compute which stats each cat has at 7.

    Returns (seven_sets, scope_7_sets) — both keyed by id(cat).
    """
    _names = stat_names or list(STAT_NAMES)
    seven_sets: dict[int, frozenset] = {
        id(c): frozenset(
            sn for sn in _names
            if get_cat_stats(c, use_current_stats, add_mutation_stats).get(sn) == 7
        )
        for c in alive
    }
    scope_7_sets: dict[int, frozenset] = {
        cid: s for cid, s in seven_sets.items() if cid in scope_set
    }
    return seven_sets, scope_7_sets


def compute_all_scores(
    alive: list,
    scope_cats: list,
    scope_set: set[int],
    seven_sets: dict[int, frozenset],
    scope_7_sets: dict[int, frozenset],
    hated_by_map: dict[int, list],
    ma_ratings: dict[str, int | None],
    stat_names: list[str],
    weights: dict[str, float],
    display_name_fn=None,
    gene_risk_lookup=None,
    use_current_stats: bool = False,
    add_mutation_stats: bool = False,
    can_breed_fn=None,
) -> tuple:
    """Run scoring for all cats.

    Returns:
        (results, cat_sub_counts, all_scores_sorted,
         all_scope_gene_risks, all_scope_children, max_7_count,
         scope_stat_sums, pair_risk_cache)
    """
    scope_stat_sums = sorted(
        sum(get_cat_stats(c, use_current_stats, add_mutation_stats).values())
        for c in scope_cats
    )
    pair_risk_cache: dict[tuple[int, int], float] = {}

    results: dict[int, ScoreResult] = {}
    cat_sub_counts: dict[int, int] = {}
    for cat in alive:
        results[id(cat)] = compute_breed_priority_score(
            cat, scope_cats, ma_ratings,
            stat_names=stat_names,
            weights=weights,
            mutation_display_name=display_name_fn,
            scope_stat_sums=scope_stat_sums,
            hated_by=hated_by_map.get(id(cat), []),
            gene_risk_lookup=gene_risk_lookup,
            gene_risk_cache=pair_risk_cache,
            use_current_stats=use_current_stats,
            add_mutation_stats=add_mutation_stats,
            can_breed_fn=can_breed_fn,
        )
        # 7-sub: penalize cats whose 7-set is strictly dominated by scope peers
        my_sevens = seven_sets.get(id(cat), frozenset())
        sub_cnt = sum(
            1 for oc, os in scope_7_sets.items()
            if oc != id(cat) and my_sevens < os
        ) if my_sevens else 0
        cat_sub_counts[id(cat)] = sub_cnt
        sub_w = weights.get("seven_sub", 0.0)
        sub_thr = max(1, int(round(weights.get("seven_sub_threshold", 1.0))))
        sub_pts = sub_w * min(sub_cnt / sub_thr, 1.0) if sub_cnt > 0 else 0.0
        results[id(cat)].subtotals["seven_sub"] = sub_pts
        results[id(cat)].total += sub_pts
        if sub_pts != 0:
            results[id(cat)].breakdown.append(("7sub", sub_pts))

    all_scores_sorted = sorted(results[id(c)].total for c in alive)

    all_scope_gene_risks = sorted(
        results[id(c)].scope_gene_risk
        for c in scope_cats
        if id(c) in results and results[id(c)].scope_gene_risk is not None
    )

    all_scope_children = sorted(
        sum(1 for ch in c.children if id(ch) in scope_set)
        for c in scope_cats
    )

    max_7_count = max(
        (sum(1 for v in get_cat_stats(c, use_current_stats, add_mutation_stats).values()
             if v == 7) for c in alive),
        default=0,
    )

    return (results, cat_sub_counts, all_scores_sorted,
            all_scope_gene_risks, all_scope_children, max_7_count,
            scope_stat_sums, pair_risk_cache)


def compute_heatmap_norms(
    results: dict[int, ScoreResult],
    alive: list,
    is_heat: bool,
    heat_algo: str,
) -> tuple[dict[int, float], dict[int, float], float]:
    """Pre-compute heatmap normalization data.

    Returns (col_max_abs, row_max_abs, score_max_abs).
    """
    col_max_abs: dict[int, float] = {}
    row_max_abs: dict[int, float] = {}
    score_max_abs: float = 1.0
    if not is_heat:
        return col_max_abs, row_max_abs, score_max_abs

    for ci, (_, keys) in enumerate(SCORE_COLUMNS):
        mx = max(
            (abs(sum(results[id(c)].subtotals.get(k, 0.0) for k in keys))
             for c in alive),
            default=0.0,
        )
        col_max_abs[ci] = mx if mx > 0 else 1.0
    smx = max((abs(results[id(c)].total) for c in alive), default=0.0)
    score_max_abs = smx if smx > 0 else 1.0
    if heat_algo == "row":
        for c in alive:
            r = results[id(c)]
            mx = max(
                (abs(sum(r.subtotals.get(k, 0.0) for k in keys))
                 for _, keys in SCORE_COLUMNS),
                default=0.0,
            )
            row_max_abs[id(c)] = mx if mx > 0 else 1.0

    return col_max_abs, row_max_abs, score_max_abs
```

- [ ] **Step 4: Update `scoring/__init__.py` with re-exports**

```python
# src/mewgenics/scoring/__init__.py
"""Automatic scoring engine — pure Python, no Qt dependencies."""

from mewgenics.scoring.engine import (  # noqa: F401
    compute_breed_priority_score,
    ScoreResult,
    priority_tier,
    ability_base,
    is_basic_trait,
    BREED_PRIORITY_WEIGHTS,
    BREED_PRIORITY_TIERS,
    WEIGHT_UI_ROWS,
    SCORE_COLUMNS,
    TRAIT_RATING_OPTIONS,
    TRAIT_LOW_THRESHOLD,
    TRAIT_HIGH_THRESHOLD,
)
from mewgenics.scoring.cat_stats import (  # noqa: F401
    get_cat_stats,
    get_mutation_stat_bonuses,
)
from mewgenics.scoring.helpers import (  # noqa: F401
    build_relationship_maps,
    compute_seven_sets,
    compute_all_scores,
    compute_heatmap_norms,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/mewgenics/scoring/helpers.py src/mewgenics/scoring/__init__.py tests/test_scoring_engine.py
git commit -m "feat(scoring): add helpers for relationship maps, seven-sets, and heatmap norms"
```

---

## Task 4: Filter State

**Files:**
- Create: `src/mewgenics/scoring/filters.py`
- Modify: `tests/test_scoring_engine.py`

- [ ] **Step 1: Write failing tests for FilterState and cat_passes_filter**

Append to `tests/test_scoring_engine.py`:

```python
from mewgenics.scoring.filters import FilterState, cat_passes_filter
from mewgenics.scoring.engine import ScoreResult


def _dummy_score(total=5.0, gene_risk=None):
    return ScoreResult(
        total=total, tier="Good", tier_color="#1ec8a0",
        breakdown=[], subtotals={}, scope_gene_risk=gene_risk,
    )


def test_filter_state_roundtrip():
    fs = FilterState()
    fs.age_active = True
    fs.age_value = 8
    fs.age_op = "Greater Than"
    d = fs.to_dict()
    fs2 = FilterState.from_dict(d)
    assert fs2.age_active is True
    assert fs2.age_value == 8
    assert fs2.age_op == "Greater Than"


def test_filter_passes_all_disabled():
    cat = _scope_cat("A", age=5)
    fs = FilterState()  # all disabled
    assert cat_passes_filter(cat, fs, _dummy_score(), set()) is True


def test_filter_age_less_than():
    fs = FilterState()
    fs.age_active = True
    fs.age_value = 10
    fs.age_op = "Less Than"
    assert cat_passes_filter(_scope_cat("Young", age=5), fs, _dummy_score(), set()) is True
    assert cat_passes_filter(_scope_cat("Old", age=15), fs, _dummy_score(), set()) is False


def test_filter_gender():
    fs = FilterState()
    fs.gender_active = True
    fs.gender_male = True
    fs.gender_female = False
    fs.gender_unknown = False
    assert cat_passes_filter(_scope_cat("M", gender="M"), fs, _dummy_score(), set()) is True
    assert cat_passes_filter(_scope_cat("F", gender="F"), fs, _dummy_score(), set()) is False


def test_filter_stat():
    fs = FilterState()
    fs.stat_filters["STR"]["active"] = True
    fs.stat_filters["STR"]["value"] = 7
    fs.stat_filters["STR"]["op"] = "Equals"
    cat7 = _scope_cat("Strong", stats={"STR": 7, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    cat5 = _scope_cat("Weak", stats={"STR": 5, "DEX": 5, "CON": 5, "INT": 5, "SPD": 5, "CHA": 5, "LCK": 5})
    assert cat_passes_filter(cat7, fs, _dummy_score(), set()) is True
    assert cat_passes_filter(cat5, fs, _dummy_score(), set()) is False


def test_filter_score():
    fs = FilterState()
    fs.score_active = True
    fs.score_value = 5.0
    fs.score_op = "Greater Than"
    assert cat_passes_filter(_scope_cat("A"), fs, _dummy_score(total=8.0), set()) is True
    assert cat_passes_filter(_scope_cat("B"), fs, _dummy_score(total=3.0), set()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring_engine.py::test_filter_state_roundtrip -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `filters.py`**

Port the `FilterState` data class and `cat_passes_filter` from Byron's `filters.py`, keeping only the pure-Python parts (no Qt dialog — that comes in the view task).

```python
# src/mewgenics/scoring/filters.py
"""Filter state and matching logic for automatic scoring.

Pure Python — no Qt dependencies. The FilterDialog UI is in the view.
"""

from __future__ import annotations

from mewgenics.scoring.engine import ScoreResult, TRAIT_LOW_THRESHOLD, TRAIT_HIGH_THRESHOLD
from mewgenics.scoring.cat_stats import get_cat_stats

STAT_NAMES = ["STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK"]


def _compare(value, op: str, target) -> bool:
    if op == "Less Than":
        return value < target
    elif op == "Equals":
        return value == target
    elif op == "Greater Than":
        return value > target
    return True


class FilterState:
    """Serializable filter configuration."""

    def __init__(self):
        self.age_active: bool = False
        self.age_value: int = 10
        self.age_op: str = "Less Than"

        self.gender_active: bool = False
        self.gender_not: bool = False
        self.gender_male: bool = True
        self.gender_female: bool = True
        self.gender_unknown: bool = True

        self.stat_filters: dict[str, dict] = {
            n: {"active": False, "value": 7, "op": "Equals"} for n in STAT_NAMES
        }

        self.sum_active: bool = False
        self.sum_value: int = 28
        self.sum_op: str = "Greater Than"

        self.count7_active: bool = False
        self.count7_value: int = 0
        self.count7_op: str = "Greater Than"

        self.aggro_active: bool = False
        self.aggro_not: bool = False
        self.aggro_low: bool = True
        self.aggro_med: bool = True
        self.aggro_high: bool = True

        self.libido_active: bool = False
        self.libido_not: bool = False
        self.libido_low: bool = True
        self.libido_med: bool = True
        self.libido_high: bool = True

        self.gene_active: bool = False
        self.gene_value: float = 0.0
        self.gene_op: str = "Equals"

        self.children_active: bool = False
        self.children_value: int = 0
        self.children_op: str = "Greater Than"

        self.score_active: bool = False
        self.score_value: float = 0.0
        self.score_op: str = "Greater Than"

        self.injury_active: bool = False

        self.location_active: bool = False
        self.location_rooms: list[str] = []

    def to_dict(self) -> dict:
        return {
            "age_active": self.age_active, "age_value": self.age_value, "age_op": self.age_op,
            "gender_active": self.gender_active, "gender_not": self.gender_not,
            "gender_male": self.gender_male, "gender_female": self.gender_female,
            "gender_unknown": self.gender_unknown,
            "stat_filters": self.stat_filters,
            "sum_active": self.sum_active, "sum_value": self.sum_value, "sum_op": self.sum_op,
            "count7_active": self.count7_active, "count7_value": self.count7_value,
            "count7_op": self.count7_op,
            "aggro_active": self.aggro_active, "aggro_not": self.aggro_not,
            "aggro_low": self.aggro_low, "aggro_med": self.aggro_med, "aggro_high": self.aggro_high,
            "libido_active": self.libido_active, "libido_not": self.libido_not,
            "libido_low": self.libido_low, "libido_med": self.libido_med, "libido_high": self.libido_high,
            "gene_active": self.gene_active, "gene_value": self.gene_value, "gene_op": self.gene_op,
            "children_active": self.children_active, "children_value": self.children_value,
            "children_op": self.children_op,
            "score_active": self.score_active, "score_value": self.score_value, "score_op": self.score_op,
            "injury_active": self.injury_active,
            "location_active": self.location_active, "location_rooms": self.location_rooms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FilterState":
        fs = cls()
        for attr in fs.__dict__:
            if attr in d:
                setattr(fs, attr, d[attr])
        return fs


def _trait_bucket(value: float | None) -> str:
    if value is None:
        return "med"
    if value < TRAIT_LOW_THRESHOLD:
        return "low"
    if value >= TRAIT_HIGH_THRESHOLD:
        return "high"
    return "med"


def _has_injury(cat) -> bool:
    base = getattr(cat, 'base_stats', {}) or {}
    total = getattr(cat, 'total_stats', {}) or {}
    for sn in STAT_NAMES:
        if total.get(sn, 0) < base.get(sn, 0):
            return True
    return False


def cat_passes_filter(
    cat,
    fs: FilterState,
    score_result: ScoreResult,
    scope_set: set[int],
) -> bool:
    """Return True if cat passes all enabled filters."""
    # Age
    if fs.age_active:
        age = getattr(cat, 'age', None)
        if age is not None and not _compare(age, fs.age_op, fs.age_value):
            return False

    # Gender
    if fs.gender_active:
        g = getattr(cat, 'gender', '?')
        allowed = set()
        if fs.gender_male:
            allowed.add('M')
        if fs.gender_female:
            allowed.add('F')
        if fs.gender_unknown:
            allowed.add('?')
        match = g in allowed
        if fs.gender_not:
            match = not match
        if not match:
            return False

    # Individual stats
    stats = getattr(cat, 'base_stats', {}) or {}
    for sn, sf in fs.stat_filters.items():
        if sf.get("active") and not _compare(stats.get(sn, 0), sf["op"], sf["value"]):
            return False

    # Stat sum
    if fs.sum_active:
        cat_sum = sum(stats.values())
        if not _compare(cat_sum, fs.sum_op, fs.sum_value):
            return False

    # 7-count
    if fs.count7_active:
        count7 = sum(1 for v in stats.values() if v == 7)
        if not _compare(count7, fs.count7_op, fs.count7_value):
            return False

    # Aggression
    if fs.aggro_active:
        bucket = _trait_bucket(getattr(cat, 'aggression', None))
        allowed = set()
        if fs.aggro_low:
            allowed.add("low")
        if fs.aggro_med:
            allowed.add("med")
        if fs.aggro_high:
            allowed.add("high")
        match = bucket in allowed
        if fs.aggro_not:
            match = not match
        if not match:
            return False

    # Libido
    if fs.libido_active:
        bucket = _trait_bucket(getattr(cat, 'libido', None))
        allowed = set()
        if fs.libido_low:
            allowed.add("low")
        if fs.libido_med:
            allowed.add("med")
        if fs.libido_high:
            allowed.add("high")
        match = bucket in allowed
        if fs.libido_not:
            match = not match
        if not match:
            return False

    # Gene risk
    if fs.gene_active and score_result.scope_gene_risk is not None:
        if not _compare(score_result.scope_gene_risk, fs.gene_op, fs.gene_value):
            return False

    # Children in scope
    if fs.children_active:
        n_children = sum(1 for ch in getattr(cat, 'children', []) if id(ch) in scope_set)
        if not _compare(n_children, fs.children_op, fs.children_value):
            return False

    # Score
    if fs.score_active:
        if not _compare(score_result.total, fs.score_op, fs.score_value):
            return False

    # Injury
    if fs.injury_active and not _has_injury(cat):
        return False

    # Location
    if fs.location_active and fs.location_rooms:
        room = getattr(cat, 'room', None) or ''
        if room not in fs.location_rooms:
            return False

    return True
```

- [ ] **Step 4: Update `scoring/__init__.py` to re-export filters**

Add to `src/mewgenics/scoring/__init__.py`:

```python
from mewgenics.scoring.filters import FilterState, cat_passes_filter  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scoring_engine.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/mewgenics/scoring/filters.py src/mewgenics/scoring/__init__.py tests/test_scoring_engine.py
git commit -m "feat(scoring): add FilterState and cat_passes_filter"
```

---

## Task 5: Shared Trait Ratings (`utils/trait_ratings.py`)

**Files:**
- Create: `src/mewgenics/utils/trait_ratings.py`
- Modify: `src/mewgenics/utils/paths.py`
- Create: `tests/test_trait_ratings.py`

- [ ] **Step 1: Add `_scoring_path` to paths.py**

```python
# Add to src/mewgenics/utils/paths.py after _gender_overrides_path:

def _scoring_path(save_path: str) -> str:
    """Return JSON path for shared scoring state (ratings + profiles)."""
    return save_path + ".scoring.json"
```

- [ ] **Step 2: Write failing tests for TraitRatings**

```python
# tests/test_trait_ratings.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_trait_ratings.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `trait_ratings.py`**

```python
# src/mewgenics/utils/trait_ratings.py
"""Shared trait desirability ratings with 5-slot profiles.

Used by both Automatic Scoring and Manual Scoring views.
Persists to a single JSON sidecar file per save.
"""

from __future__ import annotations

import json
import os
from typing import Optional


class TraitRatings:
    """Trait desirability ratings with 5-slot profile system.

    Rating values:
        2  = Top Priority
        1  = Desirable
        0  = Neutral
        None = Undecided
        -1 = Undesirable
    """

    def __init__(self, path: str):
        self._path = path
        self.active_profile: int = 1
        self.ratings: dict[str, int | None] = {}
        self.profiles: dict[int, dict] = {}
        self._auto_weights: dict[str, float] = {}
        self._auto_options: dict = {}
        self._manual_weights: dict = {}
        self._load()

    # ── Rating access ─────────────────────────────────────────────────────

    def get_rating(self, key: str) -> int | None:
        return self.ratings.get(key)

    def set_rating(self, key: str, value: int | None):
        if value is None:
            self.ratings.pop(key, None)
        else:
            self.ratings[key] = value

    # ── Weight access ─────────────────────────────────────────────────────

    def get_auto_weights(self) -> dict[str, float]:
        return dict(self._auto_weights)

    def set_auto_weights(self, weights: dict[str, float]):
        self._auto_weights = dict(weights)

    def get_auto_options(self) -> dict:
        return dict(self._auto_options)

    def set_auto_options(self, options: dict):
        self._auto_options = dict(options)

    def get_manual_weights(self) -> dict:
        return dict(self._manual_weights)

    def set_manual_weights(self, weights: dict):
        self._manual_weights = dict(weights)

    # ── Profile management ────────────────────────────────────────────────

    def switch_profile(self, slot: int):
        """Auto-save current state to outgoing slot, load incoming slot."""
        if slot == self.active_profile and slot in self.profiles:
            # Reload from saved profile
            self._load_slot(slot)
            return

        # Save current state to outgoing slot
        self.profiles[self.active_profile] = self._serialize_current()

        # Load incoming slot
        self.active_profile = slot
        if slot in self.profiles:
            self._load_slot(slot)
        else:
            # Empty slot — reset to defaults
            self.ratings = {}
            self._auto_weights = {}
            self._auto_options = {}
            self._manual_weights = {}

    def _serialize_current(self) -> dict:
        return {
            "ratings": dict(self.ratings),
            "auto_weights": dict(self._auto_weights),
            "auto_options": dict(self._auto_options),
            "manual_weights": dict(self._manual_weights),
        }

    def _load_slot(self, slot: int):
        data = self.profiles.get(slot, {})
        self.ratings = dict(data.get("ratings", {}))
        # Convert None-string keys back
        self.ratings = {k: v for k, v in self.ratings.items()}
        self._auto_weights = dict(data.get("auto_weights", {}))
        self._auto_options = dict(data.get("auto_options", {}))
        self._manual_weights = dict(data.get("manual_weights", {}))

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self):
        """Write current state to JSON file."""
        # Save current into its profile slot before writing
        self.profiles[self.active_profile] = self._serialize_current()
        data = {
            "active_profile": self.active_profile,
            "profiles": {str(k): v for k, v in self.profiles.items()},
        }
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, dict):
            return

        self.active_profile = data.get("active_profile", 1)
        raw_profiles = data.get("profiles", {})
        self.profiles = {}
        for k, v in raw_profiles.items():
            try:
                self.profiles[int(k)] = v
            except (ValueError, TypeError):
                pass

        # Load active profile's data into working state
        if self.active_profile in self.profiles:
            self._load_slot(self.active_profile)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_trait_ratings.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/mewgenics/utils/trait_ratings.py src/mewgenics/utils/paths.py tests/test_trait_ratings.py
git commit -m "feat: add shared TraitRatings with 5-slot profiles and JSON persistence"
```

---

## Task 6: Stats Overview Dialog

**Files:**
- Modify: `src/mewgenics/dialogs.py`

- [ ] **Step 1: Read the current end of `dialogs.py` to find insertion point**

Check imports and the last class in `dialogs.py` to determine where to add StatsOverviewDialog.

- [ ] **Step 2: Add StatsOverviewDialog to `dialogs.py`**

Port from Byron's `stats_overview.py::StatsOverviewDialog`, but using our styling constants from `constants.py` and `styling.py`. The key adaptation is replacing Byron's theme colors with our constants.

Add these imports at the top of `dialogs.py` (merge with existing imports):

```python
from mewgenics.scoring.cat_stats import get_cat_stats
```

Add the dialog class at the bottom of `dialogs.py`:

```python
class StatsOverviewDialog(QDialog):
    """Non-blocking popup: alive cats x current stats with injury breakdown."""

    def __init__(self, cats: list, stat_names: list | None = None,
                 room_display: dict | None = None, parent=None):
        super().__init__(parent)
        from save_parser import STAT_NAMES as _PARSER_STAT_NAMES
        self._all_cats = cats
        self._stat_names = stat_names or list(_PARSER_STAT_NAMES)
        self._room_disp = room_display or {}
        self._include_injuries = True

        n = len(self._stat_names)
        self._col_sum = 2 + n
        self._col_fx = 3 + n
        self._num_cols = 4 + n

        self.setWindowTitle("Current Stats Overview")
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setStyleSheet("background:#0a0a18; color:#d7d7e6;")
        self.resize(960, 580)

        vb = QVBoxLayout(self)
        vb.setContentsMargins(12, 12, 12, 12)
        vb.setSpacing(8)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background:#1a1a32; border-radius:4px; border-bottom:1px solid #2a2a4a;")
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(10, 6, 10, 6)
        hdr_l.setSpacing(10)
        title = QLabel("Current Stats Overview")
        title.setStyleSheet("color:#d7d7e6; font-size:14px; font-weight:bold;")
        hdr_l.addWidget(title)
        hdr_l.addStretch()
        self._chk_injuries = QCheckBox("Include injuries / effects")
        self._chk_injuries.setChecked(True)
        self._chk_injuries.setStyleSheet("color:#bbb; font-size:11px;")
        self._chk_injuries.stateChanged.connect(self._on_toggle)
        hdr_l.addWidget(self._chk_injuries)
        vb.addWidget(hdr)

        # Table
        headers = ["Name", "Loc"] + list(self._stat_names) + ["Sum", "Effects"]
        self._table = QTableWidget()
        self._table.setColumnCount(self._num_cols)
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.setStyleSheet(
            "QTableWidget { background:#0d0d1c; color:#ccc; gridline-color:#1e1e38;"
            " border:1px solid #2a2a4a; }"
            "QTableWidget::item:selected { background:#1e3060; }"
            "QHeaderView::section { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a;"
            " padding:4px; font-weight:bold; }"
        )
        self._table.verticalHeader().setVisible(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 68)
        for c in range(2, 2 + n):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, 38)
        hh.setSectionResizeMode(self._col_sum, QHeaderView.Fixed)
        self._table.setColumnWidth(self._col_sum, 44)
        hh.setSectionResizeMode(self._col_fx, QHeaderView.Interactive)
        self._table.setColumnWidth(self._col_fx, 220)
        vb.addWidget(self._table)

        # Footer
        self._note = QLabel("")
        self._note.setStyleSheet("color:#666; font-size:10px;")
        vb.addWidget(self._note)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:6px 16px; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
        )
        close_btn.clicked.connect(self.accept)
        vb.addWidget(close_btn, alignment=Qt.AlignRight)

        self._populate()

    def _on_toggle(self):
        self._include_injuries = self._chk_injuries.isChecked()
        self._populate()

    def _populate(self):
        cats = [c for c in self._all_cats if getattr(c, 'status', 'Gone') != 'Gone']
        self.setUpdatesEnabled(False)
        try:
            self._table.setSortingEnabled(False)
            self._table.setRowCount(len(cats))
            fx_count = 0
            for row, cat in enumerate(cats):
                base = getattr(cat, 'base_stats', {}) or {}
                stats = get_cat_stats(cat, self._include_injuries)
                # Name
                self._table.setItem(row, 0, QTableWidgetItem(getattr(cat, 'name', '?')))
                # Location
                raw_room = getattr(cat, 'room', '') or ''
                loc_text = 'Adv.' if getattr(cat, 'status', '') == 'Adventure' else self._room_disp.get(raw_room, raw_room or '\u2014')
                loc_item = QTableWidgetItem(loc_text)
                loc_item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row, 1, loc_item)
                # Stats
                cat_sum = 0
                for ci, sn in enumerate(self._stat_names):
                    val = stats.get(sn, 0)
                    cat_sum += val
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, val)
                    item.setTextAlignment(Qt.AlignCenter)
                    b_val = base.get(sn, 0)
                    if val > 7:
                        item.setForeground(QColor("#1ec8a0"))
                    elif val == 7:
                        item.setForeground(QColor("#1ec8a0"))
                    elif val == 6:
                        item.setForeground(QColor("#777777"))
                    elif val < 5:
                        item.setForeground(QColor("#555555"))
                    if self._include_injuries and val < b_val:
                        item.setBackground(QColor("#2a0505"))
                    self._table.setItem(row, 2 + ci, item)
                # Sum
                sum_item = QTableWidgetItem()
                sum_item.setData(Qt.DisplayRole, cat_sum)
                sum_item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row, self._col_sum, sum_item)
                # Effects
                effects = []
                for sn in self._stat_names:
                    b = base.get(sn, 0)
                    t = stats.get(sn, b)
                    if t != b:
                        effects.append((sn, t - b))
                if effects:
                    fx_count += 1
                    fx_text = ", ".join(f"{sn} {d:+d}" for sn, d in effects)
                    fx_item = QTableWidgetItem(fx_text)
                    has_neg = any(d < 0 for _, d in effects)
                    has_pos = any(d > 0 for _, d in effects)
                    if has_neg and not has_pos:
                        fx_item.setForeground(QColor("#e04040"))
                    elif has_pos and not has_neg:
                        fx_item.setForeground(QColor("#1ec8a0"))
                else:
                    fx_item = QTableWidgetItem("\u2014")
                    fx_item.setForeground(QColor("#555"))
                self._table.setItem(row, self._col_fx, fx_item)
            self._table.setSortingEnabled(True)
            self._table.sortByColumn(self._col_sum, Qt.DescendingOrder)
            mode = "effective" if self._include_injuries else "base"
            self._note.setText(f"{len(cats)} alive cats  \u00b7  {fx_count} with stat effects  \u00b7  showing {mode} stats")
        finally:
            self.setUpdatesEnabled(True)

    def refresh(self, cats: list):
        self._all_cats = cats
        self._populate()
```

Note: This depends on `QTableWidget`, `QCheckBox`, `QPushButton`, `QHeaderView`, `QAbstractItemView` which are likely already imported in `dialogs.py`. Check and add any missing imports. Also add `from mewgenics.scoring.cat_stats import get_cat_stats` to the imports.

- [ ] **Step 3: Verify the dialog imports work**

Run: `python -c "from mewgenics.dialogs import StatsOverviewDialog; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/mewgenics/dialogs.py
git commit -m "feat: add StatsOverviewDialog for current stats overview popup"
```

---

## Task 7: Auto Scoring View — Core Structure

This is the largest task. Build the view skeleton with left panel, score table, and right panel. Wire up scope, options, weights, and the recompute flow. Heatmap and filter dialog come after.

**Files:**
- Create: `src/mewgenics/views/auto_scoring.py`

- [ ] **Step 1: Create the view file with class skeleton and left panel**

This is a large file. Build it incrementally. Start with the class, `__init__`, `set_cats`, `save_session_state`, and the left panel construction.

The view follows our existing patterns: `QWidget` subclass with `set_cats(cats)` API, splitter layout, `save_session_state()`, uses `_tr()` for localization, our color constants.

Create `src/mewgenics/views/auto_scoring.py` — the full implementation. Due to the size (~800-1000 lines), this task creates the file and wires the core functionality. The implementation should reference:

- **Left panel**: Profile dropdown, display mode, scope checkboxes, options, weight grid from `WEIGHT_UI_ROWS`, filter button
- **Center**: QTableWidget with stat columns + score sub-columns + total score
- **Right panel**: Trait rating lists (abilities + mutations tabs), children list
- **Recompute flow**: `_recompute()` calls `compute_all_scores()`, applies filters, populates table
- **Heatmap rendering**: Cell background coloring based on `compute_heatmap_norms()`
- **Filter dialog**: Modal dialog built from `FilterState`

Key patterns to follow from existing views:
- `ManualScoringView` in `views/manual_scoring.py` for splitter layout, QTableWidget usage, `save_session_state()`
- `RoomOptimizerView` in `views/room_optimizer.py` for three-panel splitter pattern

The view receives a `TraitRatings` instance via `set_trait_ratings(tr)` — called by MainWindow after construction.

This step creates the complete file. Due to the length, it should be implemented directly referencing Byron's `src/breed_priority/__init__.py` for UI logic while using our codebase conventions.

- [ ] **Step 2: Verify the view imports**

Run: `python -c "from mewgenics.views.auto_scoring import AutoScoringView; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/mewgenics/views/auto_scoring.py
git commit -m "feat: add AutoScoringView with scope, weights, heatmap, filters, and trait ratings"
```

---

## Task 8: MainWindow Integration — Sidebar and View Wiring

**Files:**
- Modify: `src/mewgenics/main_window.py`

- [ ] **Step 1: Add import for AutoScoringView**

Add after the `ManualScoringView` import at the top of `main_window.py`:

```python
from mewgenics.views.auto_scoring import AutoScoringView
```

Also add:

```python
from mewgenics.utils.trait_ratings import TraitRatings
from mewgenics.utils.paths import _scoring_path
```

- [ ] **Step 2: Add member variable in `__init__`**

After `self._manual_scoring_view: Optional[ManualScoringView] = None` (around line 259), add:

```python
        self._auto_scoring_view: Optional[AutoScoringView] = None
        self._trait_ratings: Optional[TraitRatings] = None
```

- [ ] **Step 3: Add "Cat Sorting" section to `_build_sidebar()`**

In `_build_sidebar()`, insert a new section between the Fight Club button and the Breeding section separator. Replace the existing block from `vb.addWidget(_hsep())` before breeding section through the Manual Scoring button in the Info section.

After the fight club button block (line ~930), replace:

```python
        vb.addWidget(_hsep())
        self._breeding_section_label = sl(_tr("sidebar.section.breeding"))
        vb.addWidget(self._breeding_section_label)
```

with:

```python
        vb.addWidget(_hsep())
        self._sorting_section_label = sl(_tr("sidebar.section.cat_sorting", default="CAT SORTING"))
        vb.addWidget(self._sorting_section_label)
        self._btn_auto_scoring = _sidebar_btn(_tr("sidebar.button.auto_scoring", default="Automatic Scoring"))
        self._btn_auto_scoring.clicked.connect(self._open_auto_scoring_view)
        vb.addWidget(self._btn_auto_scoring)
        self._btn_manual_scoring = _sidebar_btn(_tr("sidebar.button.manual_scoring", default="Manual Scoring"))
        self._btn_manual_scoring.clicked.connect(self._open_manual_scoring_view)
        vb.addWidget(self._btn_manual_scoring)

        vb.addWidget(_hsep())
        self._breeding_section_label = sl(_tr("sidebar.section.breeding"))
        vb.addWidget(self._breeding_section_label)
```

And remove the Manual Scoring button from the Info section (the old location around line 960-962):

Remove:
```python
        self._btn_manual_scoring = _sidebar_btn(_tr("sidebar.button.manual_scoring", default="Manual Scoring"))
        self._btn_manual_scoring.clicked.connect(self._open_manual_scoring_view)
        vb.addWidget(self._btn_manual_scoring)
```

- [ ] **Step 4: Add `_ensure_auto_scoring_view()`**

After `_ensure_manual_scoring_view()`:

```python
    def _ensure_auto_scoring_view(self):
        if self._auto_scoring_view is not None:
            return
        self._auto_scoring_view = AutoScoringView(self)
        self._auto_scoring_view.hide()
        self._content_vb.addWidget(self._auto_scoring_view, 1)
        if self._trait_ratings is not None:
            self._auto_scoring_view.set_trait_ratings(self._trait_ratings)
        self._push_cats_to_view_if_loaded("auto_scoring", self._auto_scoring_view)
```

- [ ] **Step 5: Add to `_build_all_views()`**

Add `self._ensure_auto_scoring_view()` to `_build_all_views()` after `_ensure_manual_scoring_view()`.

- [ ] **Step 6: Add `_show_auto_scoring_view()` and `_open_auto_scoring_view()`**

Follow the exact same pattern as `_show_manual_scoring_view()` — hide all other views, show this one, update button states. Add the auto_scoring hide/uncheck lines to ALL existing `_show_*` methods.

```python
    def _open_auto_scoring_view(self):
        self._push_nav_history()
        _save_current_view("auto_scoring")
        self._show_auto_scoring_view()

    def _show_auto_scoring_view(self):
        self._ensure_auto_scoring_view()
        if self._active_btn is not None:
            self._active_btn.setChecked(False)
        self._active_btn = None
        if hasattr(self, "_header"):
            self._header.hide()
        if hasattr(self, "_table_view_container"):
            self._table_view_container.hide()
        # Hide all other views
        for view_attr in ("_tree_view", "_safe_breeding_view", "_breeding_partners_view",
                          "_room_optimizer_view", "_perfect_planner_view", "_calibration_view",
                          "_mutation_planner_view", "_furniture_view", "_manual_scoring_view"):
            v = getattr(self, view_attr, None)
            if v is not None:
                v.hide()
        # Show auto scoring
        if self._auto_scoring_view is not None:
            self._set_view_cats_if_needed("auto_scoring", self._auto_scoring_view, self._cats)
            self._auto_scoring_view.show()
        # Uncheck all sidebar buttons
        for btn_attr in ("_btn_tree_view", "_btn_safe_breeding_view", "_btn_breeding_partners_view",
                         "_btn_room_optimizer", "_btn_perfect_planner", "_btn_calibration",
                         "_btn_mutation_planner", "_btn_furniture_view", "_btn_manual_scoring"):
            btn = getattr(self, btn_attr, None)
            if btn is not None:
                btn.setChecked(False)
        if hasattr(self, "_btn_auto_scoring"):
            self._btn_auto_scoring.setChecked(True)
```

- [ ] **Step 7: Update all existing `_show_*` methods**

Add to every existing `_show_*` method (table, tree, safe_breeding, breeding_partners, room_optimizer, perfect_planner, calibration, mutation_planner, furniture, manual_scoring):

Hide line:
```python
        if hasattr(self, "_auto_scoring_view") and self._auto_scoring_view is not None:
            self._auto_scoring_view.hide()
```

Uncheck line:
```python
        if hasattr(self, "_btn_auto_scoring"):
            self._btn_auto_scoring.setChecked(False)
```

- [ ] **Step 8: Wire into `_on_save_loaded()`**

In `_on_save_loaded()`, after the existing cat pushes, add:

```python
            # Initialize shared trait ratings
            if self._current_save:
                scoring_path = _scoring_path(self._current_save)
                self._trait_ratings = TraitRatings(scoring_path)
                if self._auto_scoring_view is not None:
                    self._auto_scoring_view.set_trait_ratings(self._trait_ratings)
                if self._manual_scoring_view is not None:
                    self._manual_scoring_view.set_trait_ratings(self._trait_ratings)

            if self._auto_scoring_view is not None:
                self._set_view_cats_if_needed("auto_scoring", self._auto_scoring_view, cats)
```

- [ ] **Step 9: Wire into `_flush_persistent_view_state()`**

Add:

```python
        if self._auto_scoring_view is not None:
            self._auto_scoring_view.save_session_state()
        if self._trait_ratings is not None:
            self._trait_ratings.save()
```

- [ ] **Step 10: Wire into `_current_view_kind()` and `_restore_current_view()`**

Add `("auto_scoring", getattr(self, "_auto_scoring_view", None))` to the checks list in `_current_view_kind()`.

Add `"auto_scoring": self._show_auto_scoring_view` to the `_restore_map` in `_restore_current_view()`.

- [ ] **Step 11: Update localization label in `_retranslate_sidebar()`**

Find where sidebar section labels are updated (around line 1185-1189) and add:

```python
        if hasattr(self, "_sorting_section_label"):
            self._sorting_section_label.setText(_tr("sidebar.section.cat_sorting", default="CAT SORTING"))
```

- [ ] **Step 12: Verify the app launches**

Run: `python src/mewgenics_manager.py`
Expected: App launches. Sidebar shows "CAT SORTING" section with "Automatic Scoring" and "Manual Scoring" buttons. Clicking "Automatic Scoring" shows the new view.

- [ ] **Step 13: Commit**

```bash
git add src/mewgenics/main_window.py
git commit -m "feat: wire AutoScoringView into MainWindow with Cat Sorting sidebar section"
```

---

## Task 9: Manual Scoring — Profile Dropdown and Shared Ratings Integration

**Files:**
- Modify: `src/mewgenics/views/manual_scoring.py`

- [ ] **Step 1: Add TraitRatings integration**

Add import at top:

```python
from mewgenics.utils.trait_ratings import TraitRatings
```

Add member variable in `__init__` (after `self._config`):

```python
        self._trait_ratings: Optional[TraitRatings] = None
```

Add `set_trait_ratings` method:

```python
    def set_trait_ratings(self, tr: TraitRatings):
        """Receive shared TraitRatings instance from MainWindow."""
        self._trait_ratings = tr
        # Restore state from active profile
        manual_weights = tr.get_manual_weights()
        if manual_weights:
            self._restore_from_manual_weights(manual_weights)
```

- [ ] **Step 2: Add profile dropdown to config panel**

In `_build_config_panel()`, add a profile dropdown at the top of the layout (before the stat weight section):

```python
        # Profile selector
        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        profile_lbl = QLabel("Profile:")
        profile_lbl.setMinimumWidth(60)
        profile_row.addWidget(profile_lbl)
        self._profile_combo = QComboBox()
        for i in range(1, 6):
            self._profile_combo.addItem(f"Profile {i}", i)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self._profile_combo, 1)
        profile_row.addStretch()
        vb.addLayout(profile_row)
```

- [ ] **Step 3: Implement profile switching**

```python
    def _on_profile_changed(self):
        if self._suppress_recompute or self._trait_ratings is None:
            return
        slot = self._profile_combo.currentData()
        if slot is None:
            return
        # Save current manual weights before switching
        self._trait_ratings.set_manual_weights(self._read_config())
        self._trait_ratings.switch_profile(slot)
        self._trait_ratings.save()
        # Load new profile's manual weights
        manual_weights = self._trait_ratings.get_manual_weights()
        if manual_weights:
            self._restore_from_manual_weights(manual_weights)
        # Sync mutation selections from shared ratings
        self._sync_from_shared_ratings()
        self._recompute()
```

- [ ] **Step 4: Bridge mutation selectors to shared ratings**

When a mutation is checked/unchecked in Manual Scoring, update the shared ratings:

```python
    def _sync_to_shared_ratings(self):
        """Push mutation selections to shared TraitRatings."""
        if self._trait_ratings is None:
            return
        desired = set(self._desired_selector.get_checked())
        undesired = set(self._undesired_selector.get_checked())
        desired_dis = set(self._desired_disorder_selector.get_checked())
        undesired_dis = set(self._undesired_disorder_selector.get_checked())
        # Update ratings for all known mutations
        for m in self._all_mutations:
            if m in desired or m in desired_dis:
                self._trait_ratings.set_rating(m, 1)
            elif m in undesired or m in undesired_dis:
                self._trait_ratings.set_rating(m, -1)
            else:
                self._trait_ratings.set_rating(m, None)

    def _sync_from_shared_ratings(self):
        """Pull mutation selections from shared TraitRatings."""
        if self._trait_ratings is None:
            return
        desired = set()
        undesired = set()
        for m in self._all_mutations:
            rating = self._trait_ratings.get_rating(m)
            if rating is not None and rating > 0:
                desired.add(m)
            elif rating == -1:
                undesired.add(m)
        # Rebuild selectors will pick up new checked sets on next set_cats
```

- [ ] **Step 5: Update `save_session_state` to use TraitRatings**

Modify `save_session_state` to save to shared TraitRatings when available:

```python
    def save_session_state(self):
        if self._trait_ratings is not None:
            self._trait_ratings.set_manual_weights(self._read_config())
            self._sync_to_shared_ratings()
            self._trait_ratings.save()
        else:
            # Fallback to old persistence
            state = self._read_config()
            state["threshold"] = self._spin_threshold.value()
            state["room_filter"] = self._room_combo.currentData() or ""
            state["in_house_only"] = self._chk_in_house.isChecked()
            state["splitter_sizes"] = self._splitter.sizes()
            hdr = self._table.horizontalHeader()
            state["sort_column"] = hdr.sortIndicatorSection()
            state["sort_order"] = hdr.sortIndicatorOrder().value
            _save_ui_state(self._UI_STATE_KEY, state)
```

- [ ] **Step 6: Add `_restore_from_manual_weights` helper**

```python
    def _restore_from_manual_weights(self, s: dict):
        """Restore widget state from a manual_weights dict."""
        self._suppress_recompute = True
        self._spin_stat.setValue(s.get("stat_weight", _DEFAULT_CONFIG["stat_weight"]))
        self._desired_selector.set_state(
            use_individual=s.get("desired_use_individual", False),
            default_weight=s.get("desired_default_weight", 1),
            per_weights=s.get("desired_mutation_weights", {}),
        )
        self._undesired_selector.set_state(
            use_individual=s.get("undesired_use_individual", False),
            default_weight=s.get("undesired_default_weight", -5),
            per_weights=s.get("undesired_mutation_weights", {}),
        )
        self._desired_disorder_selector.set_state(
            use_individual=s.get("desired_disorder_use_individual", False),
            default_weight=s.get("desired_disorder_default_weight", 1),
            per_weights=s.get("desired_disorder_weights", {}),
        )
        self._undesired_disorder_selector.set_state(
            use_individual=s.get("undesired_disorder_use_individual", False),
            default_weight=s.get("undesired_disorder_default_weight", -5),
            per_weights=s.get("undesired_disorder_weights", {}),
        )
        for k, spin in self._spin_inbredness.items():
            spin.setValue(s.get("inbredness_weights", _DEFAULT_CONFIG["inbredness_weights"]).get(k, 0))
        for k, spin in self._spin_libido.items():
            spin.setValue(s.get("libido_weights", _DEFAULT_CONFIG["libido_weights"]).get(k, 0))
        for k, spin in self._spin_aggression.items():
            spin.setValue(s.get("aggression_weights", _DEFAULT_CONFIG["aggression_weights"]).get(k, 0))
        self._spin_passive.setValue(s.get("passive_weight", _DEFAULT_CONFIG["passive_weight"]))
        self._spin_spell.setValue(s.get("extra_spell_weight", _DEFAULT_CONFIG["extra_spell_weight"]))
        for k, spin in self._spin_sexuality.items():
            spin.setValue(s.get("sexuality_weights", _DEFAULT_CONFIG["sexuality_weights"]).get(k, 0))
        self._suppress_recompute = False
        self._config = self._read_config()
```

- [ ] **Step 7: Verify Manual Scoring still works**

Run: `python src/mewgenics_manager.py`
Expected: Manual Scoring view loads. Profile dropdown visible. Switching profiles changes weights.

- [ ] **Step 8: Commit**

```bash
git add src/mewgenics/views/manual_scoring.py
git commit -m "feat: add profile dropdown and shared TraitRatings to Manual Scoring"
```

---

## Task 10: Run Full Test Suite and Fix Issues

**Files:**
- Possibly modify: any files with test failures

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ --basetemp=tmp/pytest -v`

- [ ] **Step 2: Fix any failures**

Address test failures. Common issues:
- Import path changes from new `scoring/` package
- Mock objects missing new attributes (`visual_mutation_entries`, etc.)
- Existing tests affected by Manual Scoring persistence changes

- [ ] **Step 3: Run tests again to confirm all pass**

Run: `pytest tests/ --basetemp=tmp/pytest -v`
Expected: All tests PASS (except `test_perfect_planner_ui.py` which was pre-existing failure)

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve test failures from scoring integration"
```

---

## Task 11: Final Verification and Version Bump

**Files:**
- Modify: `VERSION`

- [ ] **Step 1: Manual smoke test**

Run the app: `python src/mewgenics_manager.py`

Verify:
1. Sidebar shows "CAT SORTING" section with Automatic Scoring and Manual Scoring
2. Clicking Automatic Scoring opens the view
3. Score table populates with cats when a save is loaded
4. Scope checkboxes work (toggling rooms changes scores)
5. Weight sliders affect scores
6. Heatmap toggle works
7. Display mode (Score/Values/Both) works
8. Filter dialog opens and filters apply
9. Trait rating changes in right panel affect scores
10. Profile switching works (saves/loads state)
11. Manual Scoring still works, profile dropdown visible
12. Mutation selections sync between views
13. "Current Stats..." opens StatsOverviewDialog
14. State persists between app restarts

- [ ] **Step 2: Bump version**

```bash
echo "5.7.0" > VERSION
```

- [ ] **Step 3: Commit**

```bash
git add VERSION
git commit -m "v5.7.0: Automatic Scoring view with shared trait ratings and profiles"
```
