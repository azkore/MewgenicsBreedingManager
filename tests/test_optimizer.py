import os
import sys
from types import SimpleNamespace

_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(_proj_root, "src")
sys.path.insert(0, _src_dir)
sys.path.insert(0, _proj_root)

from room_optimizer import (
    OptimizationParams,
    RoomConfig,
    RoomType,
    best_breeding_room_stimulation,
    build_room_configs,
    optimize_room_distribution,
)
import room_optimizer.optimizer as room_optimizer_impl
from breeding import PairFactors, PairProjection
from save_parser import STAT_NAMES


def _make_cat(
    db_key: int,
    *,
    gender: str,
    sexuality: str = "straight",
    room: str = "Floor1_Large",
    generation: int = 0,
    parent_a=None,
    parent_b=None,
    must_breed: bool = False,
    disorders=None,
    aggression: float = 0.3,
    libido: float = 0.7,
    stat_seed: int = 5,
):
    return SimpleNamespace(
        db_key=db_key,
        name=f"Cat{db_key}",
        gender=gender,
        sexuality=sexuality,
        gender_display=gender,
        status="In House",
        room=room,
        room_display=room,
        generation=generation,
        parent_a=parent_a,
        parent_b=parent_b,
        must_breed=must_breed,
        disorders=list(disorders or []),
        aggression=aggression,
        libido=libido,
        base_stats={stat: stat_seed for stat in STAT_NAMES},
        haters=[],
        lovers=[],
    )


def _room_for_cat(result, db_key: int) -> str | None:
    for assignment in result.rooms:
        if any(cat.db_key == db_key for cat in assignment.cats):
            return assignment.room.key
    return None


def test_build_room_configs_preserves_roles():
    configs = build_room_configs(
        [
            {"room": "Floor1_Large", "type": "breeding"},
            {"room": "Attic", "type": "fallback"},
        ],
        available_rooms=["Floor1_Large", "Attic"],
    )

    assert [cfg.key for cfg in configs] == ["Floor1_Large", "Attic"]
    assert configs[0].room_type == RoomType.BREEDING
    assert configs[1].room_type == RoomType.FALLBACK


def test_build_room_configs_uses_capacity_and_room_stimulation():
    room_stats = {"Floor1_Large": SimpleNamespace(raw_effects={"Stimulation": 17.0})}
    configs = build_room_configs(
        [
            {"room": "Floor1_Large", "type": "breeding", "max_cats": 4},
            {"room": "Attic", "type": "fallback", "max_cats": 0},
        ],
        available_rooms=["Floor1_Large", "Attic"],
        room_stats=room_stats,
    )

    assert configs[0].max_cats == 4
    assert configs[0].base_stim == 17.0
    assert configs[1].max_cats is None
    assert best_breeding_room_stimulation(configs) == 17.0


def test_optimize_room_distribution_finds_same_sex_pair():
    cat_a = _make_cat(1, gender="male", sexuality="bi", must_breed=True, stat_seed=8)
    cat_b = _make_cat(2, gender="male", sexuality="bi", must_breed=True, stat_seed=8)
    cat_c = _make_cat(3, gender="female", sexuality="straight", stat_seed=4)

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 2, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b, cat_c],
        room_configs,
        OptimizationParams(max_risk=10.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    paired_ids = {
        tuple(sorted((pair.cat_a.db_key, pair.cat_b.db_key)))
        for assignment in result.rooms
        for pair in assignment.pairs
    }

    assert (1, 2) in paired_ids
    assert result.stats.total_pairs >= 1


def test_optimize_room_distribution_uses_disjoint_room_pairs():
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=8)
    cat_b = _make_cat(2, gender="female", sexuality="bi", stat_seed=8)
    cat_c = _make_cat(3, gender="male", sexuality="bi", stat_seed=7)
    cat_d = _make_cat(4, gender="female", sexuality="bi", stat_seed=7)

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 4, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b, cat_c, cat_d],
        room_configs,
        OptimizationParams(max_risk=10.0, avoid_lovers=False, use_sa=False),
        cache=None,
        excluded_keys=set(),
    )

    breeding_assignment = next(
        assignment for assignment in result.rooms if assignment.room.key == "Floor1_Large"
    )
    paired_cat_ids = [
        cat_id
        for pair in breeding_assignment.pairs
        for cat_id in (pair.cat_a.db_key, pair.cat_b.db_key)
    ]

    assert len(breeding_assignment.pairs) == 2
    assert len(set(paired_cat_ids)) == 4
    assert result.stats.total_pairs == 2


def test_optimize_room_distribution_keep_lovers_together_does_not_block_other_pairs():
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=8)
    cat_b = _make_cat(2, gender="female", sexuality="bi", stat_seed=8)
    cat_c = _make_cat(3, gender="male", sexuality="bi", stat_seed=6)
    cat_d = _make_cat(4, gender="female", sexuality="bi", stat_seed=6)
    cat_a.lovers = [cat_b]
    cat_b.lovers = [cat_a]

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 4, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b, cat_c, cat_d],
        room_configs,
        OptimizationParams(max_risk=10.0, avoid_lovers=True, use_sa=False),
        cache=None,
        excluded_keys=set(),
    )

    breeding_room = _room_for_cat(result, 1)
    assert breeding_room == "Floor1_Large"
    assert breeding_room == _room_for_cat(result, 2)
    assert breeding_room == _room_for_cat(result, 3)
    assert breeding_room == _room_for_cat(result, 4)
    assert result.stats.assigned_cats == 4
    assert result.stats.total_pairs == 2


def test_optimize_room_distribution_allows_unrequited_love_pairs_when_avoid_lovers_is_on():
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=8)
    cat_b = _make_cat(2, gender="female", sexuality="bi", stat_seed=8)
    cat_a.lovers = [cat_b]

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 2, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b],
        room_configs,
        OptimizationParams(max_risk=10.0, avoid_lovers=True, use_sa=False),
        cache=None,
        excluded_keys=set(),
    )

    assert result.stats.total_pairs == 1
    assert _room_for_cat(result, 1) == "Floor1_Large"
    assert _room_for_cat(result, 2) == "Floor1_Large"


def test_optimize_room_distribution_enforces_risk_cutoff():
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=6)
    cat_b = _make_cat(2, gender="female", sexuality="straight", stat_seed=6)

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 2, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b],
        room_configs,
        OptimizationParams(max_risk=1.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    assert result.stats.total_pairs == 0
    assert all(not assignment.pairs for assignment in result.rooms)


def test_optimize_room_distribution_keeps_empty_rooms_in_result():
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=8)
    cat_b = _make_cat(2, gender="female", sexuality="bi", stat_seed=8)

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor1_Small", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor2_Small", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor2_Large", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [cat_a, cat_b],
        room_configs,
        OptimizationParams(max_risk=10.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    assert [assignment.room.key for assignment in result.rooms] == [cfg.key for cfg in room_configs]
    assert result.stats.assigned_cats == 2


def test_optimize_room_distribution_family_mode_separates_siblings():
    dad = _make_cat(1, gender="male", sexuality="bi")
    mom = _make_cat(2, gender="female", sexuality="bi")
    sibling_a = _make_cat(3, gender="male", sexuality="bi", parent_a=dad, parent_b=mom, generation=1)
    sibling_b = _make_cat(4, gender="female", sexuality="bi", parent_a=dad, parent_b=mom, generation=1)
    unrelated = _make_cat(5, gender="male", sexuality="bi")

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor1_Small", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]
    result = optimize_room_distribution(
        [dad, mom, sibling_a, sibling_b, unrelated],
        room_configs,
        OptimizationParams(mode_family=True, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    assert _room_for_cat(result, 3) != _room_for_cat(result, 4)


def test_optimize_room_distribution_family_mode_runs_sa(monkeypatch):
    cat_a = _make_cat(1, gender="male", sexuality="bi", stat_seed=8)
    cat_b = _make_cat(2, gender="female", sexuality="bi", stat_seed=8)
    cat_c = _make_cat(3, gender="male", sexuality="bi", stat_seed=5)

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor1_Small", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]

    calls = []

    def _fake_run_sa_refinement(**kwargs):
        calls.append(kwargs)
        return kwargs["room_assignments"]

    monkeypatch.setattr(room_optimizer_impl, "_run_sa_refinement", _fake_run_sa_refinement)

    result = optimize_room_distribution(
        [cat_a, cat_b, cat_c],
        room_configs,
        OptimizationParams(mode_family=True, use_sa=True, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    assert calls
    assert calls[0]["mode_family"] is True
    assert result.stats.total_cats == 3


def test_throughput_mode_skips_singletons_that_do_not_add_pairs(monkeypatch):
    cats = [
        _make_cat(1, gender="male", sexuality="bi", stat_seed=8),
        _make_cat(2, gender="female", sexuality="bi", stat_seed=8),
        _make_cat(3, gender="male", sexuality="bi", stat_seed=7),
        _make_cat(4, gender="female", sexuality="bi", stat_seed=7),
    ]

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 2, 50.0),
        RoomConfig("Floor1_Small", RoomType.BREEDING, 1, 50.0),
        RoomConfig("Attic", RoomType.FALLBACK, None, 50.0),
    ]

    valid_pairs = {
        (1, 2): 100.0,
        (3, 4): 90.0,
    }

    def _fake_score_pair_factors(cat_a, cat_b, **_kwargs):
        pair_key = tuple(sorted((cat_a.db_key, cat_b.db_key)))
        compatible = pair_key in valid_pairs
        return PairFactors(
            cat_a=cat_a,
            cat_b=cat_b,
            compatible=compatible,
            reason="" if compatible else "blocked",
            risk=0.0 if compatible else 100.0,
            projection=PairProjection(
                expected_stats={stat: 0.0 for stat in STAT_NAMES},
                stat_ranges={stat: (0, 0) for stat in STAT_NAMES},
                locked_stats=(),
                reachable_stats=(),
                missing_stats=(),
                sum_range=(0, 0),
                avg_expected=0.0,
                seven_plus_total=0.0,
                distance_total=0.0,
            ),
            complementarity_bonus=0.0,
            variance_penalty=0.0,
            personality_bonus=0.0,
            trait_bonus=0.0,
            must_breed_bonus=0.0,
            lover_bonus=0.0,
            quality=valid_pairs.get(pair_key, 0.0),
        )

    monkeypatch.setattr(room_optimizer_impl, "score_pair_factors", _fake_score_pair_factors)

    result = optimize_room_distribution(
        cats,
        room_configs,
        OptimizationParams(
            max_risk=10.0,
            avoid_lovers=False,
            maximize_throughput=True,
        ),
        cache=None,
        excluded_keys=set(),
    )

    small_room = next(
        assignment for assignment in result.rooms if assignment.room.key == "Floor1_Small"
    )
    fallback_room = next(
        assignment for assignment in result.rooms if assignment.room.key == "Attic"
    )

    assert small_room.cats == []
    assert sorted(cat.db_key for cat in fallback_room.cats) == [3, 4]


# ---------------------------------------------------------------------------
# Regression tests for DP cap / greedy fallback (issues #63, #64)
# ---------------------------------------------------------------------------

def test_large_room_greedy_fallback_completes_quickly():
    """With 30 cats in one breeding room (> _MAX_DP_CATS), the optimizer must
    complete in bounded time using the greedy fallback instead of the
    exponential bitmask DP."""
    import time

    cats = []
    for i in range(30):
        gender = "male" if i % 2 == 0 else "female"
        cats.append(_make_cat(i + 1, gender=gender, sexuality="bi", stat_seed=5 + (i % 3)))

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, None, 50.0),  # unlimited capacity
    ]
    start = time.monotonic()
    result = optimize_room_distribution(
        cats,
        room_configs,
        OptimizationParams(max_risk=100.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )
    elapsed = time.monotonic() - start

    assert elapsed < 30.0, f"Optimizer took {elapsed:.1f}s — greedy fallback should be fast"
    assert result.stats.total_pairs >= 1
    # Verify pairs are non-overlapping
    used_ids = set()
    for assignment in result.rooms:
        for pair in assignment.pairs:
            assert pair.cat_a.db_key not in used_ids, "Overlapping pair detected"
            assert pair.cat_b.db_key not in used_ids, "Overlapping pair detected"
            used_ids.add(pair.cat_a.db_key)
            used_ids.add(pair.cat_b.db_key)


def test_no_fallback_room_does_not_hang():
    """When all rooms are breeding rooms (no fallback), overflow cats end up
    in the last breeding room.  The DP cap must prevent this from hanging."""
    import time

    cats = []
    for i in range(40):
        gender = "male" if i % 2 == 0 else "female"
        cats.append(_make_cat(i + 1, gender=gender, sexuality="bi", stat_seed=5))

    # All rooms are breeding rooms with cap 6 — only 12 cats fit, 28 overflow
    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, 6, 50.0),
        RoomConfig("Floor1_Small", RoomType.BREEDING, 6, 50.0),
    ]
    start = time.monotonic()
    result = optimize_room_distribution(
        cats,
        room_configs,
        OptimizationParams(max_risk=100.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )
    elapsed = time.monotonic() - start

    assert elapsed < 30.0, f"Optimizer took {elapsed:.1f}s with no fallback room"
    assert result.stats.assigned_cats == 40


def test_greedy_fallback_produces_reasonable_pairs():
    """The greedy approach should find at least as many pairs as a naive
    first-fit, even when it can't use the exact DP."""
    cats = []
    for i in range(28):
        gender = "male" if i % 2 == 0 else "female"
        cats.append(_make_cat(i + 1, gender=gender, sexuality="bi", stat_seed=6))

    room_configs = [
        RoomConfig("Floor1_Large", RoomType.BREEDING, None, 50.0),
    ]
    result = optimize_room_distribution(
        cats,
        room_configs,
        OptimizationParams(max_risk=100.0, avoid_lovers=False),
        cache=None,
        excluded_keys=set(),
    )

    # 14 males + 14 females with bi sexuality → at least 14 pairs possible
    # (greedy should find most of them)
    assert result.stats.total_pairs >= 10, (
        f"Expected at least 10 pairs from 28 bi cats, got {result.stats.total_pairs}"
    )
