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
