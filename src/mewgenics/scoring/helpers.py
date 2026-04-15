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
