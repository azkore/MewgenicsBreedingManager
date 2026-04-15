# Automatic Scoring View — Design Spec

## Overview

A new "Automatic Scoring" view that scores individual cats for breeding value using scope-aware analysis. Complements the existing Manual Scoring view. Both views share trait desirability ratings and a 5-slot profile system via a common persistence layer.

Ported from byronaltice/MewgenicsBreedingManager's `breed_priority` module. Scoring algorithms are preserved; UI is rebuilt from scratch to follow our codebase conventions (`_tr()`, our constants/colors, our config patterns).

## File Layout

```
src/mewgenics/
  scoring/
    __init__.py              # Package init, re-exports public API
    engine.py                # compute_breed_priority_score(), ScoreResult,
                             #   priority_tier(), BREED_PRIORITY_WEIGHTS,
                             #   WEIGHT_UI_ROWS, SCORE_COLUMNS, BREED_PRIORITY_TIERS
    helpers.py               # build_relationship_maps(), compute_seven_sets(),
                             #   compute_all_scores(), compute_heatmap_norms()
    cat_stats.py             # get_cat_stats(), get_mutation_stat_bonuses()
  utils/
    trait_ratings.py          # TraitRatings — shared ratings + 5-slot profiles
  views/
    auto_scoring.py           # AutoScoringView
  dialogs.py                  # + StatsOverviewDialog (added to existing)
```

### Separation of Concerns

- `scoring/` is pure Python with zero Qt dependencies. Testable and portable.
- `utils/trait_ratings.py` owns shared state between Manual and Auto scoring.
- `views/auto_scoring.py` is the Qt view, following existing view patterns.
- `StatsOverviewDialog` is a dialog, not a view — lives in `dialogs.py`.

## Scoring Engine (`scoring/`)

### `engine.py` — Core Scoring Function

`compute_breed_priority_score(cat, scope_cats, ma_ratings, stat_names, weights, ...) -> ScoreResult`

Scores an individual cat considering:

1. **Stat 7 rarity** — Bonus per stat at 7, scaled down when many scope cats share it. Sole owner gets 2x. Configurable threshold (`stat_7_threshold`, default 7) for when scaling kicks in.
2. **7-count bonus** — Flat bonus (`stat_7_count`, default 2.0) per stat a cat personally has at 7.
3. **7-sub dominance** — Penalty when other scope cats strictly dominate this cat's 7-set (they have all your 7s plus more). Weight `seven_sub`, threshold `seven_sub_threshold`.
4. **Stat sum percentile** — Score based on percentile rank in scope. 90th+ = full weight, 75th+ = weight-1, 50th+ = weight-2, below = 0.
5. **Trait ratings** — User-rated abilities/mutations. Sole owner of Top Priority trait gets 2x `trait_top_priority` weight. Shared traits divided by scope count. Undesirable = flat `trait_undesirable` penalty.
6. **Personality** — Aggression low=`low_aggression`, high=`high_aggression`. Libido high=`high_libido`, low=`low_libido`. Thresholds at 0.3 (low) and 0.7 (high).
7. **Genetic safety** — Average risk% with all breedable scope partners. Below `gene_risk_threshold` (default 2%) = `zero_risk_bonus`. Above = `no_children` * scaled penalty via `gene_risk_penalty_scale`.
8. **Age penalty** — `age_penalty` weight, escalating per 3 years over `age_threshold` (default 10).
9. **CHA penalty** — `cha_low` weight at CHA=4 (1x), CHA=3 (2x). Default 0.
10. **Sexuality** — `gay_pref`, `bi_pref` weights. Both default 0 (no bias).
11. **Gender** — `unknown_gender` bonus for ? gender (default 1.0).
12. **Relationships** — `love_interest` / `rivalry` for scope-wide. `love_interest_room` / `rivalry_room` for same-room. Includes reverse "hated by" detection.

**Default weights** (`BREED_PRIORITY_WEIGHTS`):

```python
{
    "stat_7": 5.0, "stat_7_threshold": 7.0, "stat_7_count": 2.0,
    "trait_top_priority": 2.0, "trait_desirable": 2.0, "trait_undesirable": -2.0,
    "low_aggression": 1.0, "high_aggression": -1.0,
    "unknown_gender": 1.0,
    "high_libido": 0.5, "low_libido": -0.5,
    "gay_pref": 0.0, "bi_pref": 0.0,
    "no_children": -2.0, "zero_risk_bonus": 2.0,
    "gene_risk_threshold": 2.0, "gene_risk_penalty_scale": 10.0,
    "stat_sum": 4.0,
    "age_penalty": -2.0, "age_threshold": 10.0,
    "love_interest": 1.0, "rivalry": -2.0,
    "love_interest_room": 0.0, "rivalry_room": 0.0,
    "seven_sub": 0.0, "seven_sub_threshold": 1.0,
    "cha_low": 0.0,
}
```

**Tier classification:**

| Score    | Tier     | Color   |
|----------|----------|---------|
| 10+      | Keep     | Gold    |
| 4–9      | Good     | Teal    |
| 0–3      | Neutral  | Gray    |
| -5 to -1 | Consider | Orange  |
| < -5     | Cull     | Red     |

**`ScoreResult`** — Return type with `total`, `tier`, `tier_color`, `breakdown` (list of (label, points) tuples), `subtotals` (dict of weight_key -> accumulated points), `scope_gene_risk`.

### `helpers.py` — Pre-computation Helpers

Called once per recompute cycle:

- `build_relationship_maps(cats)` → `(hated_by_map, loved_by_map)` — Reverse lookups keyed by `id(target_cat)`.
- `compute_seven_sets(alive, scope_set, use_current_stats, add_mutation_stats)` → `(seven_sets, scope_7_sets)` — Frozensets of which stats each cat has at 7.
- `compute_all_scores(alive, scope_cats, ...)` → `(results, cat_sub_counts, all_scores_sorted, all_scope_gene_risks, all_scope_children, max_7_count, scope_stat_sums, pair_risk_cache)` — Runs engine for all cats, computes 7-sub, collects aggregate data.
- `compute_heatmap_norms(results, alive, is_heat, heat_algo)` → `(col_max_abs, row_max_abs, score_max_abs)` — Max-absolute values for heatmap normalization.

### `cat_stats.py` — Stat Resolution

`get_cat_stats(cat, use_current: bool, add_mutation_stats: bool) -> dict[str, int]`

- `use_current=False` → `cat.base_stats`
- `use_current=True` → `cat.total_stats` (falls back to base_stats)
- `add_mutation_stats=True` → Parses `visual_mutation_entries` detail fields for stat deltas (e.g. "+2 CON, -1 DEX") and adds them on top.

`get_mutation_stat_bonuses(cat) -> dict[str, int]` — Regex extraction from mutation detail strings.

## Shared Trait Ratings (`utils/trait_ratings.py`)

### Rating Values

| Value  | Label        | Auto Scoring Effect                    | Manual Scoring Effect |
|--------|-------------|----------------------------------------|-----------------------|
| `2`    | Top Priority | Sole owner 2x, shared ÷n              | Desired list          |
| `1`    | Desirable    | Sole owner 2x, shared ÷n              | Desired list          |
| `0`    | Neutral      | No score contribution                  | Neither list          |
| `None` | Undecided    | No score contribution                  | Neither list          |
| `-1`   | Undesirable  | Flat penalty                           | Undesired list        |

### Data Model

```python
class TraitRatings:
    ratings: dict[str, int | None]     # trait_key -> rating value
    profiles: dict[int, ProfileSlot]   # slots 1-5
    active_profile: int                # currently active slot
```

Rating keys: ability base names (e.g. `"Vurp"` not `"Vurp2"`) for abilities, raw mutation/defect names for mutations.

### Profile Slots

Each slot stores a complete snapshot:

```json
{
  "active_profile": 1,
  "profiles": {
    "1": {
      "ratings": {"Vurp": 1, "TankSwap": 2},
      "auto_weights": {"stat_7": 5.0, "stat_sum": 4.0},
      "auto_options": {"hide_kittens": false, "display_mode": "score", "scope": {}, "filters": {}, "sort_col": -1, "sort_desc": true, "heatmap_on": false, "heat_algo": "column", "show_stats": false, "use_current_stats": false, "add_mutation_stats": false, "hide_out_of_scope": false},
      "manual_weights": {"stat_weight": 1, "libido_weights": {}, "aggression_weights": {}, "inbredness_weights": {}, "desired_default_weight": 1, "undesired_default_weight": -5, "desired_use_individual": false, "undesired_use_individual": false, "desired_mutation_weights": {}, "undesired_mutation_weights": {}, "passive_weight": 1, "extra_spell_weight": 0, "sexuality_weights": {}, "desired_disorder_default_weight": 1, "undesired_disorder_default_weight": -5, "desired_disorder_use_individual": false, "undesired_disorder_use_individual": false, "desired_disorder_weights": {}, "undesired_disorder_weights": {}}
    }
  }
}
```

### Persistence

- Single JSON file: `{save_dir}/{save_name}_scoring.json`
- Loaded during `_on_save_loaded()` in MainWindow.
- Saves on every change (debounced, 600ms timer) + final save on app close via `_flush_persistent_view_state()`.
- Manual Scoring's current `_save_ui_state`/`_load_ui_state` persistence migrates to this file.

### Profile Switching

Automatic on dropdown change:
1. Serialize current state (ratings + auto_weights + auto_options + manual_weights) into outgoing slot.
2. Load incoming slot's data.
3. Update `active_profile`.
4. Trigger save (debounced).
5. Emit signal so both views refresh.

### Cross-View Sharing

- MainWindow owns the `TraitRatings` instance, passes reference to both views.
- When either view changes a rating, the instance updates and emits a signal. The other view refreshes on next recompute.
- Ratings are shared across views. Weights are view-specific (stored per profile, but under separate keys).

## Auto Scoring View (`views/auto_scoring.py`)

### Layout

Three-panel splitter (left | center | right):

**Left panel** (scrollable, fixed-ish width):
1. **Profile** — Dropdown, 5 slots, auto-save on switch.
2. **Display** — Score/Values/Both toggle. Heatmap on/off + Column/Row algo. Show Stats checkbox. "Current Stats..." button.
3. **Scope** — "All Cats" checkbox + per-room checkboxes with gender breakdown (M/F/?) and average risk.
4. **Options** — Hide Kittens, Hide Out-of-Scope, Use Current Stats, Add Mutation Stats.
5. **Weights** — Grid built from `WEIGHT_UI_ROWS`. Sliders with labels, organized by category with separators.
6. **Filters** — Button opens FilterDialog.

**Center — Score table** (QTableWidget):
- Columns: Name | Location | STR DEX CON INT SPD CHA LCK | [sep] | Sum Age 7rare 7cnt 7sub CHA Sex Lib Gender Gene Aggro HateScope HateRoom LoveScope LoveRoom Trait | [sep] | Score
- Heatmap overlay: colored cell backgrounds from normalization data.
- Sortable by any column.
- Row selection drives right panel content.
- Tier coloring on Score column.

**Right panel** (scrollable):
1. **Trait tables** — Two list widgets (tabs or stacked): Abilities, Mutations & Defects. Each row = trait name + rating dropdown. Writes to shared `TraitRatings`.
2. **Children list** — Selected cat's offspring in scope.
3. **Top breeding risks** — Top partners by genetic risk % for selected cat.

### Heatmap

Two algorithms:
- **Column normalization** — Each score sub-column normalized by max absolute value across all visible cats. Green for positive, red for negative, intensity proportional to magnitude.
- **Row normalization** — Each cat's sub-columns normalized by that cat's max absolute sub-score. Shows relative strengths within a cat.

Toggle and algorithm selector in the Display section of the left panel.

### Scope vs Filters

- **Scope** determines which cats are included in scoring calculations (7-rarity counts, gene risk averaging, trait sharing counts).
- **Filters** determine which cats are *visible* in the table. A filtered-out cat still counts toward scope if it's in a scoped room.

### Recompute Flow

```
User changes scope/weights/ratings/options
  → recompute()
    → build_relationship_maps()
    → compute_seven_sets()
    → compute_all_scores()  (runs engine for each cat)
    → compute_heatmap_norms()
    → apply filters
    → populate table
```

## Filter Dialog

Modal dialog opened from Filters button. Each row has an enable/disable toggle.

| Filter           | Controls                                    |
|------------------|---------------------------------------------|
| Age              | op (< / = / >) + int value                 |
| Gender           | M / F / ? checkboxes + negate toggle        |
| Individual stats | Per-stat (STR..LCK) op + int value          |
| Stat sum         | op + int value                              |
| 7-count          | op + int value                              |
| Aggression       | Low / Med / High checkboxes + negate        |
| Libido           | Low / Med / High checkboxes + negate        |
| Gene risk        | op + float value (average risk %)           |
| Children in scope| op + int value                              |
| Score            | op + float value                            |
| Injuries         | has any (checkbox)                          |
| Location         | room multiselect                            |

`FilterState` is a plain data class (no Qt) with `to_dict()`/`from_dict()` for JSON serialization. Stored in profile slots under `auto_options.filters`.

`cat_passes_filter(cat, filter_state, score_result, scope_set) -> bool` — Pure function, testable.

## Stats Overview Dialog

`StatsOverviewDialog` added to `dialogs.py`. Non-blocking popup showing all alive cats' stats.

- Table: Name | Location | 7 stat columns | Sum | Effects
- "Include injuries / effects" checkbox toggles base vs total stats.
- Effects column shows stat deltas (e.g. "CON -1, SPD -2") with color coding.
- Per-cell tooltips show base + mod + sec breakdown.
- Sortable by any column.
- Opened from "Current Stats..." button in Auto Scoring left panel.

## Manual Scoring Changes

1. **Profile dropdown** added to top of left panel (same 5 slots, same auto-save).
2. **Persistence migrated** from `_save_ui_state`/`_load_ui_state` to shared `_scoring.json` under `manual_weights` per profile.
3. **Mutation selectors** backed by shared `TraitRatings`: checking "desired" sets rating to 1, checking "undesired" sets to -1, unchecking sets to None.
4. **Per-mutation weight spinboxes** remain — these are Manual-specific overrides stored in `manual_weights` per profile. The shared rating determines which list, the spinbox determines how much.
5. **Scoring function** `compute_cat_score()` unchanged.

## Sidebar Changes

New "Cat Sorting" section between Filters and Breeding:

```
FILTERS
  All Cats / Alive Cats / Exceptional / Donation / Fight Club
──────────────
CAT SORTING
  Automatic Scoring
  Manual Scoring
──────────────
BREEDING
  Room Optimizer / Perfect 7 Planner / ...
```

Manual Scoring button moves from Info section to Cat Sorting section.

## MainWindow Integration

Standard view wiring (same pattern as all existing views):
- `self._auto_scoring_view: Optional[AutoScoringView] = None`
- `_ensure_auto_scoring_view()` — construct, hide, add to `_content_vb`, push cats
- `_show_auto_scoring_view()` — hide all others, show, update sidebar buttons
- `_open_auto_scoring_view()` — push nav history, save current view, call show
- Added to `_build_all_views()`, `_on_save_loaded()` cat push, `_flush_persistent_view_state()`, `_current_view_kind()`, `_restore_current_view()`
- All existing `_show_*` methods get hide/uncheck for the new view

**Shared `TraitRatings` instance:**
- Created by MainWindow during `_on_save_loaded()` (needs save path).
- Passed to both Auto Scoring and Manual Scoring views.
- Both read/write the same instance.
- Profile switch in either view emits a signal; the other view refreshes.

## Testing

### `tests/test_auto_scoring.py` — Scoring Engine

- `compute_breed_priority_score()` with known inputs: tier classification, 7-rarity scaling with varying scope sizes, sole-owner 2x bonus, gene risk averaging, trait rating scoring with shared/sole traits.
- `build_relationship_maps()` — reverse lookup correctness.
- `compute_seven_sets()` — dominance detection (strict subset check).
- `get_cat_stats()` — base vs total vs mutation-bonus modes.
- `get_mutation_stat_bonuses()` — regex parsing of detail strings.
- `priority_tier()` — boundary values for each tier.
- `cat_passes_filter()` — filter state application.

### `tests/test_trait_ratings.py` — Shared Ratings

- JSON round-trip (save then load, verify equality).
- Profile switch: auto-saves outgoing, loads incoming, active_profile updates.
- Rating changes visible from both views' perspective.
- Migration from old Manual Scoring format.
- Empty/missing file handling (fresh defaults).
- 5 profile slots with independent data.

### No UI tests

View-level UI tests are not added — consistent with existing views. Scoring logic is thoroughly tested at the engine level.
