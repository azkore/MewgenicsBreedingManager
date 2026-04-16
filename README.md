# Mewgenics Breeding Manager

A Python desktop tool for managing your Mewgenics cats. Reads your save file directly, scores every cat for breeding priority, optimizes room layouts, and helps plan multi-generation lines — all while tracking lineage, inbreeding risk, and trait inheritance.

Current release: `v5.7.0`

If you'd like to support the project, you can [here](https://ko-fi.com/frankieg33).

## Screenshots

### Main Page

![Main Page](Sceenshots/Home%20Screen.png)

### Breeding Optimizer

![Breeding Optimizer](Sceenshots/Room%20Optimizer.png)

### Perfect 7 Planner

![Perfect 7 Planner](Sceenshots/Perfect%207%20Planner.png)

## Features

### Cat Sorting

Two views for evaluating which cats to keep, breed, or cull:

- **Automatic Scoring** — assigns a breed priority score to every cat based on configurable weights: stat rarity, genetic safety, trait ratings, personality, age, and relationships. Includes heatmap mode, scope filtering by room, and 5 independent profiles for different strategies.
- **Manual Scoring** — assign point values to individual stats, mutations, and traits, then sort by total. Great for targeted goals like "high STR melee cats" or "collect all rare mutations."
- Shared trait rating profiles — rate abilities as Top Priority, Desirable, or Undesirable. Ratings sync between both scoring views.

### Breeding & Genetics

- Compare any pair with inheritance odds, expected offspring stats, and inbreeding risk
- Full ancestry tracking — generation depth, shared ancestors, coefficient of inbreeding
- Mating Pair Search finds safe breeding partners with compatibility scoring
- Breeding Partners grid shows all pair combinations at a glance

### Room Optimizer

- Assigns cats to rooms to maximize breeding outcomes
- Movement-aware scoring accounts for relocation cost
- Configurable room capacity, type (breeding/fallback/general), and stimulation
- Avoids trait loss from high-Evolution or high-Health rooms
- Routes kittens to fallback rooms until they're old enough to breed

### Perfect 7 Planner

- Plans multi-generation lines toward all-7 stat cats
- Simulated annealing solver finds optimal breeding chains
- Foundation pair selection with depth control

### Other Tools

- Family Tree browser with in-game cat sprite rendering
- Mutation & Disorder Planner for targeting specific traits
- Furniture Viewer showing per-room stat effects
- Live save file watching — auto-refreshes when the game saves
- Ability and mutation descriptions from `resources.gpak`

## Install

```bash
git clone https://github.com/frankieg33/MewgenicsBreedingManager
cd MewgenicsBreedingManager
pip install -r requirements.txt
python src/mewgenics_manager.py
```

On Windows you can also run `run.bat` which auto-installs dependencies on first run.

The app looks for `resources.gpak` in common Steam paths, the configured save root, and the working directory. If it can't find it, you'll be prompted to browse for it.

## Build

```bash
# Windows
build.bat

# Linux
build.sh
```

Produces a standalone executable via PyInstaller.

## Requirements

- Python 3.14+
- PySide6
- lz4
- openpyxl

## Credits

- Save parsing research based on [pzx521521/mewgenics-save-editor](https://github.com/pzx521521/mewgenics-save-editor)
- Community reverse-engineering help from players and mod users
- PR contributors: [0demongamer0](https://github.com/0demongamer0), [An-on-im](https://github.com/An-on-im), [byronaltice](https://github.com/byronaltice), [heartskingu](https://github.com/heartskingu), [ICaxapl](https://github.com/ICaxapl), [luisMolina95](https://github.com/luisMolina95), [TheMegax](https://github.com/TheMegax)
- Simulated annealing (SA) idea from [PurpleMyst](https://github.com/PurpleMyst/mewgenics_breeding_helper)
- Original idea and reference from frankieg33

## Release Notes

### v5.7.0

- New **Automatic Scoring** view — ranks every cat with a breed priority score based on stat rarity (7rare), genetic safety risk, trait ratings, personality (libido, aggression, sexuality), age, love/hate relationships, and stat sum percentile. Configurable weights, heatmap mode, scope filtering by room, and 5 independent profiles
- New **Trait Ratings** system — rate abilities and mutations as Top Priority, Desirable, Neutral, or Undesirable. Ratings are shared between Automatic and Manual Scoring views via 5-slot profiles with JSON persistence
- Manual Scoring profile dropdown — switch between trait rating profiles directly from the Manual Scoring config panel
- Stats Overview dialog — popup showing stat distribution across all cats
- Background scoring thread — heavy computation runs off the main thread so the UI stays responsive
- Pre-computed scope data — eliminates redundant O(N*S) per-cat work for stat counts, trait counts, and scope stats
- Lazy view computation — Automatic Scoring only computes when the view is visible; scores are cached until cat data changes
- Startup splash screen with progress indicator during shape extraction and save loading
- Comprehensive tooltips for all Automatic Scoring weights, options, display modes, and score columns
- Updated onboarding tutorial with Cat Sorting walkthrough (Automatic and Manual Scoring)

### v5.6.2

- Tier-2 ability support — upgraded passive abilities parsed from save, shown with "+" suffix and green-tinted chips (cherry-picked from byronaltice fork)
- GPAK ability descriptions preferred over hardcoded lookup; multi-language text extraction with BOM-aware decoding
- Generic mutation disambiguation — mutations with identical names now append their stat description
- Tooltip detail deduplication when detail already appears in display name
- Eager view loading — all views build at startup and receive cat data immediately, eliminating tab-switch freezes

### v5.6.0

- Game-accurate compatibility formula (`0.15 * CHA * libido * lover_mult * sexuality_mult`) displayed as a color-coded chip with per-attempt success % in the pair detail panel
- Ability inheritance chances (stimulation-based: first active, second active, passive) shown inline with candidate labels
- Disorder inheritance (15% per parent + inbred disorder roll based on COI) shown as chips in the risk row
- Compatibility integrated into optimizer pipeline — pairs below 5% are rejected early (performance win), quality scores scale with compatibility factor
- Stimulation inheritance weight unclamped to allow negative values per wiki mechanics
- Soft warnings instead of hard blocks for edge-case sexuality pairings; only hard-blocks when both cats have near-zero compatibility
- ? gender cats bypass sexuality scoring entirely (issue #75)
- Manual Scoring: added disorder selectors, cross-cat mutation disambiguation, QCheckBox state fix, filter buttons, undesired mutation persistence fix

### v5.5.0

- New Manual Scoring view — assign configurable point weights to stats, desired/undesirable mutations, inbredness, libido, aggression, passives, spells, and sexuality, then sort and filter cats by total score
- Instant view switching when cat data hasn't changed — generation counter skips redundant rebuilds
- Lazy data propagation — only the visible view receives cat data updates

### v5.4.9

- Lowered optimizer bitmask DP threshold from 24 to 22 cats per room
- Rewrote `_kinship()` from recursive to iterative stack-based evaluation
- Replaced O(V * Depth) generation depth computation with O(V) memoized DFS
- Fixed room button rebuild, quick room refresh re-filtering, and broken test imports

### v5.4.8

- Fixed room config bleeding between save files
- Room Optimizer routes kittens to fallback rooms
- Room Optimizer avoids placing cats with desired mutations into trait-loss rooms
