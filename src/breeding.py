"""Shared breeding compatibility and scoring helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from save_parser import (
    Cat,
    STAT_NAMES,
    can_breed,
    risk_percent,
    shared_ancestor_counts,
    _stimulation_inheritance_weight,
)

logger = logging.getLogger("mewgenics.breeding")


@dataclass(slots=True)
class PairProjection:
    """Expected offspring stat projection for a breeding pair."""

    expected_stats: dict[str, float]
    stat_ranges: dict[str, tuple[int, int]]
    locked_stats: tuple[str, ...]
    reachable_stats: tuple[str, ...]
    missing_stats: tuple[str, ...]
    sum_range: tuple[int, int]
    avg_expected: float
    seven_plus_total: float
    distance_total: float

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


@dataclass(slots=True)
class PairFactors:
    """Complete score breakdown for a breeding pair."""

    cat_a: Cat
    cat_b: Cat
    compatible: bool
    reason: str
    risk: float
    projection: PairProjection
    complementarity_bonus: float
    variance_penalty: float
    personality_bonus: float
    trait_bonus: float
    must_breed_bonus: float
    lover_bonus: float
    quality: float
    stat_priority_bonus: float = 0.0


def pair_key(a: Cat, b: Cat) -> tuple[int, int]:
    """Normalized pair key — smaller db_key first."""
    ak, bk = a.db_key, b.db_key
    return (ak, bk) if ak < bk else (bk, ak)


def planner_pair_bias(a: Cat, b: Cat) -> float:
    """
    Heuristic bias for planner suggestions.

    Prefer sexuality-compatible pairs, with a soft bias toward opposite-sex
    pairs or a cat with unknown/ditto-like gender.
    """
    if planner_pair_allows_breeding(a, b):
        return 10.0
    return -30.0


def planner_pair_allows_breeding(a: Cat, b: Cat) -> bool:
    """
    Hard planner rule that follows the game's sexuality compatibility.

    Same-sex pairs are allowed when their sexuality permits it, and straight
    same-sex pairs remain blocked.
    """
    return can_breed(a, b)[0]


def planner_inbreeding_penalty(a: Cat, b: Cat) -> float:
    """
    Conservative penalty for pairs that share ancestry.

    The perfect planner should strongly prefer unrelated pairs so repeated use
    does not quietly drift into low-grade inbreeding.
    """
    shared_total, shared_recent = shared_ancestor_counts(a, b, recent_depth=3, max_depth=8)
    return shared_total * 6.0 + shared_recent * 4.0


def is_hater_conflict(a: Cat, b: Cat, hater_key_map: dict[int, set[int]]) -> bool:
    """Check if either cat hates the other."""
    return b.db_key in hater_key_map.get(a.db_key, set()) or a.db_key in hater_key_map.get(b.db_key, set())


def is_mutual_lover_pair(a: Cat, b: Cat, lover_key_map: dict[int, set[int]]) -> bool:
    """Check if both cats are mutual lovers."""
    return b.db_key in lover_key_map.get(a.db_key, set()) and a.db_key in lover_key_map.get(b.db_key, set())


def is_lover_conflict(
    a: Cat,
    b: Cat,
    lover_key_map: dict[int, set[int]],
    avoid_lovers: bool,
) -> bool:
    """Lover relationships are a soft signal and never hard-block a pair.

    Lover exclusivity is enforced at the room assignment level by the
    optimizer's ``_filter_lover_exclusivity()`` rather than at pair evaluation
    time.  This function intentionally returns False for all inputs; the
    ``avoid_lovers`` parameter is retained for API compatibility with
    ``evaluate_pair()``.
    """
    return False


def trait_or_default(v: Optional[float], default: float = 0.5) -> float:
    """Clamp a trait value to [0, 1], using default if None."""
    return default if v is None else max(0.0, min(1.0, float(v)))


def personality_score(cats: list[Cat], prefer_low_aggression: bool, prefer_high_libido: bool) -> float:
    """Score personality traits for a group of cats."""
    score = 0.0
    n = len(cats)
    if not n:
        return 0.0
    if prefer_low_aggression:
        score += sum(1.0 - trait_or_default(c.aggression) for c in cats) / n
    if prefer_high_libido:
        score += sum(trait_or_default(c.libido) for c in cats) / n
    return score


def is_direct_family_pair(a: Cat, b: Cat, parent_key_map: dict[int, set[int]]) -> bool:
    """Check if two cats are parent-child or siblings."""
    parents_a = parent_key_map.get(a.db_key, set())
    parents_b = parent_key_map.get(b.db_key, set())
    if a.db_key in parents_b or b.db_key in parents_a:
        return True
    return bool(parents_a & parents_b)


def tracked_offspring(a: Cat, b: Cat) -> list[Cat]:
    """
    Return the direct offspring already tracked in the save for a breeding pair.

    The result is deduplicated and keeps the order from the first parent that
    lists the child, which makes the tracker stable across refreshes.
    """
    a_children = list(getattr(a, "children", []) or [])
    b_children = list(getattr(b, "children", []) or [])
    if not a_children or not b_children:
        return []

    a_keys = {child.db_key for child in a_children}
    b_keys = {child.db_key for child in b_children}
    ordered: list[Cat] = []
    seen: set[int] = set()

    for child in a_children:
        if child.db_key in b_keys and child.db_key not in seen:
            ordered.append(child)
            seen.add(child.db_key)

    for child in b_children:
        if child.db_key in a_keys and child.db_key not in seen:
            ordered.append(child)
            seen.add(child.db_key)

    return ordered


def _cat_has_trait(cat: Cat, category: str, trait_key: str) -> bool:
    if category == "mutation":
        return any(m.lower() == trait_key for m in getattr(cat, "mutations", []) or [])
    if category == "defect":
        return any(d.lower() == trait_key for d in getattr(cat, "defects", []) or [])
    if category == "passive":
        return any(p.lower() == trait_key for p in getattr(cat, "passive_abilities", []) or [])
    if category == "disorder":
        return any(d.lower() == trait_key for d in getattr(cat, "disorders", []) or [])
    if category == "ability":
        return any(a.lower() == trait_key for a in getattr(cat, "abilities", []) or [])
    return False


def _stat_priority_bonus(projection: PairProjection, stat_priority: Optional[Sequence[str]]) -> float:
    ordered: list[str] = []
    for stat in stat_priority or ():
        key = str(stat or "").strip().upper()
        if key in STAT_NAMES and key not in ordered:
            ordered.append(key)
    if not ordered:
        return 0.0

    weights = [1.75, 1.45, 1.2, 1.0, 0.85, 0.7, 0.55]
    total_weight = 0.0
    weighted_total = 0.0
    for index, stat in enumerate(ordered):
        weight = weights[index] if index < len(weights) else max(0.35, weights[-1] - 0.05 * (index - len(weights) + 1))
        weighted_total += projection.expected_stats.get(stat, 0.0) * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0

    weighted_expected = weighted_total / total_weight
    return (weighted_expected - projection.avg_expected) * 4.0


def pair_projection(cat_a: Cat, cat_b: Cat, stimulation: float = 50.0) -> PairProjection:
    """Predict offspring stat ranges and expected values for a pair."""
    better_stat_chance = _stimulation_inheritance_weight(stimulation)
    expected_stats: dict[str, float] = {}
    stat_ranges: dict[str, tuple[int, int]] = {}
    locked_stats: list[str] = []
    reachable_stats: list[str] = []
    missing_stats: list[str] = []
    seven_plus_total = 0.0
    distance_total = 0.0

    for stat in STAT_NAMES:
        stat_a = cat_a.base_stats[stat]
        stat_b = cat_b.base_stats[stat]
        lo = min(stat_a, stat_b)
        hi = max(stat_a, stat_b)
        stat_ranges[stat] = (lo, hi)
        expected = hi * better_stat_chance + lo * (1.0 - better_stat_chance)
        expected_stats[stat] = expected
        distance_total += abs(expected - 7.0)
        if lo >= 7:
            locked_stats.append(stat)
            reachable_stats.append(stat)
            seven_plus_total += 1.0
        elif hi >= 7:
            reachable_stats.append(stat)
            seven_plus_total += better_stat_chance
        else:
            missing_stats.append(stat)

    return PairProjection(
        expected_stats=expected_stats,
        stat_ranges=stat_ranges,
        locked_stats=tuple(locked_stats),
        reachable_stats=tuple(reachable_stats),
        missing_stats=tuple(missing_stats),
        sum_range=(sum(lo for lo, _ in stat_ranges.values()), sum(hi for _, hi in stat_ranges.values())),
        avg_expected=sum(expected_stats.values()) / len(STAT_NAMES),
        seven_plus_total=seven_plus_total,
        distance_total=distance_total,
    )


def evaluate_pair(
    a: Cat,
    b: Cat,
    *,
    hater_key_map: dict[int, set[int]],
    lover_key_map: dict[int, set[int]],
    avoid_lovers: bool,
    cache=None,
    parent_key_map: Optional[dict[int, set[int]]] = None,
    pair_eval_cache: Optional[dict] = None,
) -> tuple[bool, str, float]:
    """
    Unified pair evaluation. Returns (can_breed, reason, risk_pct).

    Pass parent_key_map to enable direct-family checking.
    """
    if pair_eval_cache is not None:
        key = pair_key(a, b)
        cached = pair_eval_cache.get(key)
        if cached is not None:
            return cached

    ok, reason = can_breed(a, b)

    if ok and parent_key_map is not None and is_direct_family_pair(a, b, parent_key_map):
        ok, reason = False, "Direct family pair"

    if ok and is_hater_conflict(a, b, hater_key_map):
        ok, reason = False, "These cats hate each other"

    if ok and is_lover_conflict(a, b, lover_key_map, avoid_lovers):
        ok, reason = False, "Lover relationship blocks this pair"

    if ok:
        if cache is not None and getattr(cache, "ready", False):
            get_risk = getattr(cache, "get_risk", None)
            if callable(get_risk):
                risk = get_risk(a, b)
            else:
                risk = risk_percent(a, b)
        else:
            risk = risk_percent(a, b)
    else:
        risk = 0.0

    result = (ok, reason, risk)
    if pair_eval_cache is not None:
        pair_eval_cache[pair_key(a, b)] = result
    return result


def score_pair(
    a: Cat,
    b: Cat,
    *,
    hater_key_map: Optional[dict[int, set[int]]] = None,
    lover_key_map: Optional[dict[int, set[int]]] = None,
    avoid_lovers: bool = False,
    parent_key_map: Optional[dict[int, set[int]]] = None,
    pair_eval_cache: Optional[dict] = None,
    cache=None,
    stimulation: float = 50.0,
    minimize_variance: bool = True,
    prefer_low_aggression: bool = True,
    prefer_high_libido: bool = True,
    planner_traits: Optional[Sequence[dict]] = None,
    stat_priority: Optional[Sequence[str]] = None,
    must_breed_bonus: float = 1000.0,
    lover_bonus: float = 500.0,
) -> PairFactors:
    """Return a complete score breakdown for a pair."""
    hater_key_map = hater_key_map or {}
    lover_key_map = lover_key_map or {}
    planner_traits = planner_traits or ()

    compatible, reason, risk = evaluate_pair(
        a,
        b,
        hater_key_map=hater_key_map,
        lover_key_map=lover_key_map,
        avoid_lovers=avoid_lovers,
        cache=cache,
        parent_key_map=parent_key_map,
        pair_eval_cache=pair_eval_cache,
    )

    projection = pair_projection(a, b, stimulation=stimulation)
    complementarity_bonus = sum(0.5 for stat in STAT_NAMES if max(a.base_stats[stat], b.base_stats[stat]) >= 8)
    variance_penalty = sum(
        abs(a.base_stats[stat] - b.base_stats[stat]) * 2.0
        for stat in STAT_NAMES
        if minimize_variance and abs(a.base_stats[stat] - b.base_stats[stat]) > 2
    )
    personality_bonus = personality_score([a, b], prefer_low_aggression, prefer_high_libido) * 2.5

    trait_bonus = 0.0
    for t in planner_traits:
        category = str(t.get("category", ""))
        key = str(t.get("key", ""))
        wf = float(t.get("weight", 0)) / 10.0
        if not key:
            continue
        a_has = _cat_has_trait(a, category, key)
        b_has = _cat_has_trait(b, category, key)
        if a_has or b_has:
            trait_bonus += wf * 5.0
            if a_has and b_has:
                trait_bonus += wf * 2.5

    stat_priority_bonus = _stat_priority_bonus(projection, stat_priority)

    quality = 0.0
    must_breed_total = 0.0
    lover_total = 0.0
    if compatible:
        quality = (projection.avg_expected + complementarity_bonus) * (1.0 - risk / 200.0)
        quality -= variance_penalty
        quality += personality_bonus + trait_bonus + stat_priority_bonus
        if getattr(a, "must_breed", False) or getattr(b, "must_breed", False):
            quality += must_breed_bonus
            must_breed_total = must_breed_bonus
        if is_mutual_lover_pair(a, b, lover_key_map):
            quality += lover_bonus
            lover_total = lover_bonus

    return PairFactors(
        cat_a=a,
        cat_b=b,
        compatible=compatible,
        reason=reason,
        risk=risk,
        projection=projection,
        complementarity_bonus=complementarity_bonus,
        variance_penalty=variance_penalty,
        personality_bonus=personality_bonus,
        trait_bonus=trait_bonus,
        stat_priority_bonus=stat_priority_bonus,
        must_breed_bonus=must_breed_total,
        lover_bonus=lover_total,
        quality=quality,
    )
