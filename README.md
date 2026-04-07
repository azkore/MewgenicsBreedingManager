# Mewgenics Breeding Manager

A high-performance, Python-based tool for optimizing breeding operations in Mewgenics. It extracts data directly from your save files and helps you compare pairings, optimize room layouts, and plan long-term lines to maximize strong offspring while minimizing inbreeding risk.

Current release: `v5.1.1`

If you'd like to support the project, you can [here](https://ko-fi.com/frankieg33).

## Screenshots

### Main Page

![Main Page](Sceenshots/Home%20Screen.png)

### Breeding Optimizer

![Breeding Optimizer](Sceenshots/Room%20Optimizer.png)

### Perfect 7 Planner

![Perfect 7 Planner](Sceenshots/Perfect%207%20Planner.png)

## Core Features

- Load your save file and keep your full roster, lineage, and relationships in one place
- Compare pairings with inheritance odds, expected offspring stats, and risk
- Optimize room layouts with movement-aware scoring
- Plan long-term perfect-stat lines with the Perfect 7 planner
- Read ability and mutation text from `resources.gpak` when available

## Install

This project uses `pip` and `requirements.txt`.

```bash
git clone https://github.com/frankieg33/MewgenicsBreedingManager
cd MewgenicsBreedingManager
pip install -r requirements.txt
python src/mewgenics_manager.py
```

The app will automatically look for `resources.gpak` in common Steam install paths, the app's configured save root, or in the current working directory.

## Build

```bash
build.bat
```

On Linux, use `build.sh`.

## Requirements

- Python 3.14
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

### v5.0.0

- Full codebase refactoring: split monolithic `mewgenics_manager.py` (~19k lines) into a structured `mewgenics/` package
- New package layout: `utils/`, `models/`, `workers/`, `views/`, `panels/`, `dialogs` — 30+ focused modules
- Entry point (`mewgenics_manager.py`) is now a thin wrapper for backwards compatibility
- No feature changes or behavior differences — pure structural refactor
- Updated PyInstaller spec with all new submodule imports

### v4.4.1

- Follow-up release for the same planner, optimizer, localization, and test updates shipped in `v4.4.0`
- Keeps the shared optimizer search settings, deeper room optimizer controls, breeding partner improvements, and planner persistence updates in sync with the latest release line

### v4.4.0

- Added shared optimizer search settings so the room optimizer and Perfect 7 planner use the same simulated annealing controls
- Expanded the room optimizer with deeper search options, clearer setup/configuration tabs, and improved room-related tooltips
- Improved the breeding partners view to distinguish mutual and one-way love links
- Refined the mutation planner so cats are shown alongside selected traits instead of being buried behind room filters
- Updated the saved UI defaults and persistence behavior for the new planner and optimizer settings
- Expanded localization coverage for the new settings, labels, and status messages
- Added and updated tests around planner persistence, optimizer behavior, trait labels, and UI interactions
