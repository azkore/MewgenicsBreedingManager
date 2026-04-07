#!/usr/bin/env python3
"""
Mewgenics Breeding Manager legacy compatibility entry point.

The application now lives under the ``mewgenics`` package, but tests and older
scripts still import a flat ``mewgenics_manager`` module. This bridge keeps
those imports working while delegating real behavior into the package modules.
"""

import multiprocessing
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from save_parser import (
    FurnitureDefinition,
    FurnitureItem,
    ROOM_DISPLAY,
    STAT_NAMES,
    _combined_malady_chance,
)

from mewgenics.app import main
from mewgenics.main_window import MainWindow
from mewgenics.models.breeding_cache import BreedingCache, _breeding_save_signature
from mewgenics.panels.room_priority import RoomPriorityPanel
from mewgenics.utils import calibration as _calibration
from mewgenics.utils import config as _config
from mewgenics.utils import optimizer_settings as _optimizer_settings
from mewgenics.utils import paths as _paths
from mewgenics.utils import planner_state as _planner_state
from mewgenics.utils import thresholds as _thresholds
from mewgenics.utils.abilities import (
    _ABILITY_DESC,
    _ABILITY_LOOKUP,
    _ability_tip,
    _trait_selector_summary,
)
from mewgenics.utils.cat_analysis import _cat_uid
from mewgenics.views.breeding_partners import BreedingPartnersView
from mewgenics.views.family_tree import FamilyTreeBrowserView
from mewgenics.views.furniture import FurnitureView
from mewgenics.views.mutation_planner import (
    MutationDisorderPlannerView,
    _planner_trait_style,
    _planner_trait_summary_for_cat,
    _planner_trait_summary_for_pair,
)
from mewgenics.views.perfect_planner import (
    PerfectCatPlannerView,
    PerfectPlannerFoundationPairsPanel,
    PerfectPlannerOffspringTracker,
)
from mewgenics.views.room_optimizer import RoomOptimizerCatLocator, RoomOptimizerView
from mewgenics.views.safe_breeding import SafeBreedingView
from mewgenics.workers.optimizer_worker import RoomOptimizerWorker
from breeding import score_pair as score_pair_factors


APPDATA_CONFIG_DIR = _paths.APPDATA_CONFIG_DIR
APP_CONFIG_PATH = _paths.APP_CONFIG_PATH
_save_root_dir = _config._save_root_dir

_apply_calibration_data = _calibration._apply_calibration_data
_effective_thresholds_for_cats = _thresholds._effective_thresholds_for_cats
_learn_gender_token_map = _calibration._learn_gender_token_map
_load_calibration_data = _calibration._load_calibration_data
_save_calibration_data = _calibration._save_calibration_data
_load_gender_overrides = _calibration._load_gender_overrides
_default_room_priority_config = _optimizer_settings._default_room_priority_config
_planner_pair_uid_key = _planner_state._planner_pair_uid_key


def _sync_legacy_paths():
    """Propagate monkeypatched legacy path globals into the package modules."""
    global APPDATA_CONFIG_DIR, APP_CONFIG_PATH
    APPDATA_CONFIG_DIR = str(APPDATA_CONFIG_DIR)
    APP_CONFIG_PATH = str(APP_CONFIG_PATH)
    try:
        os.makedirs(APPDATA_CONFIG_DIR, exist_ok=True)
    except Exception:
        pass
    _paths.APPDATA_CONFIG_DIR = APPDATA_CONFIG_DIR
    _paths.APP_CONFIG_PATH = APP_CONFIG_PATH
    _config.APPDATA_CONFIG_DIR = APPDATA_CONFIG_DIR
    _config.APP_CONFIG_PATH = APP_CONFIG_PATH


def _load_ui_state(key: str) -> dict:
    _sync_legacy_paths()
    return _config._load_ui_state(key)


def _save_ui_state(key: str, state: dict):
    _sync_legacy_paths()
    return _config._save_ui_state(key, state)


def _saved_room_optimizer_auto_recalc(default: bool = False) -> bool:
    _sync_legacy_paths()
    return _config._saved_room_optimizer_auto_recalc(default)


def _set_room_optimizer_auto_recalc(enabled: bool):
    _sync_legacy_paths()
    return _config._set_room_optimizer_auto_recalc(enabled)


def _load_optimizer_search_settings() -> dict:
    _sync_legacy_paths()
    return _optimizer_settings._load_optimizer_search_settings()


def _save_optimizer_search_settings(settings: dict) -> bool:
    _sync_legacy_paths()
    return _optimizer_settings._save_optimizer_search_settings(settings)


def _load_threshold_preferences() -> dict:
    _sync_legacy_paths()
    return _thresholds._load_threshold_preferences()


def _save_threshold_preferences(prefs: dict) -> bool:
    _sync_legacy_paths()
    return _thresholds._save_threshold_preferences(prefs)


def _load_planner_state_value(key: str, default=None, save_path: str | None = None):
    _sync_legacy_paths()
    return _planner_state._load_planner_state_value(key, default, save_path)


def _save_planner_state_value(key: str, value, save_path: str | None = None, *, mirror_global: bool = False):
    _sync_legacy_paths()
    return _planner_state._save_planner_state_value(key, value, save_path, mirror_global=mirror_global)


def _load_perfect_planner_foundation_pairs(save_path: str | None = None) -> list[dict]:
    _sync_legacy_paths()
    return _planner_state._load_perfect_planner_foundation_pairs(save_path)


def _save_perfect_planner_foundation_pairs(config: list[dict], save_path: str | None = None):
    _sync_legacy_paths()
    return _planner_state._save_perfect_planner_foundation_pairs(config, save_path)


def _load_perfect_planner_selected_offspring(save_path: str | None = None) -> dict[str, str]:
    _sync_legacy_paths()
    return _planner_state._load_perfect_planner_selected_offspring(save_path)


def _save_perfect_planner_selected_offspring(config: dict[str, str], save_path: str | None = None):
    _sync_legacy_paths()
    return _planner_state._save_perfect_planner_selected_offspring(config, save_path)


def find_save_files() -> list[str]:
    base = Path(_save_root_dir())
    if not base.is_dir():
        return []
    saves: list[str] = []
    for profile in base.iterdir():
        saves_dir = profile / "saves"
        if saves_dir.is_dir():
            saves.extend(str(path) for path in saves_dir.glob("*.sav"))
    saves.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return saves


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
