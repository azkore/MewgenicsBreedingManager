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
