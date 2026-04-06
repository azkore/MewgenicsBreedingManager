"""Locale catalog, translation function, and language management."""
import sys
import os
import json
import datetime
from typing import Optional

from save_parser import STAT_NAMES

from mewgenics.utils.paths import (
    APPDATA_CONFIG_DIR, LOCALES_DIR, _bundle_dir, _app_dir,
)
from mewgenics.utils.config import _load_app_config, _save_app_config


_SUPPORTED_LANGUAGES = {
    "en": "language.english",
    "zh_CN": "language.zh_cn",
    "ru": "language.ru",
    "pl": "language.pl",
}
_LOCALE_CACHE: dict[str, dict[str, str]] = {}
_LOCALE_LOGGED: set[str] = set()
_CURRENT_LANGUAGE = "en"

# ── Mutable localized lookups (updated by _refresh_localized_constants) ──────
ROOM_DISPLAY = {
    "Floor1_Large":   "1F Left",
    "Floor1_Small":   "1F Right",
    "Floor2_Small":   "2F Left",
    "Floor2_Large":   "2F Right",
    "Attic":          "Attic",
}
STATUS_ABBREV = {
    "In House":  "House",
    "Adventure": "Away",
    "Gone":      "Gone",
}
COLUMNS: list[str] = []


def _locale_log_path() -> str:
    return os.path.join(APPDATA_CONFIG_DIR, "translation_debug.log")


def _log_locale_event(language: str, message: str):
    key = f"{language}:{message}"
    if key in _LOCALE_LOGGED:
        return
    _LOCALE_LOGGED.add(key)
    try:
        with open(_locale_log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def _log_startup_environment():
    if not getattr(sys, "frozen", False):
        return
    _log_locale_event(
        "startup",
        "startup "
        f"executable={sys.executable}; "
        f"bundle_dir={_bundle_dir()}; "
        f"app_dir={_app_dir()}; "
        f"cwd={os.getcwd()}; "
        f"appdata={os.environ.get('APPDATA', '')}; "
        f"config_dir={APPDATA_CONFIG_DIR}",
    )


def _load_locale_catalog(language: str) -> dict[str, str]:
    cached = _LOCALE_CACHE.get(language)
    if cached is not None:
        return cached

    candidate_paths: list[str] = []
    for path in (
        os.path.join(LOCALES_DIR, f"{language}.json"),
        os.path.join(_bundle_dir(), f"{language}.json"),
        os.path.join(_app_dir(), "locales", f"{language}.json"),
        os.path.join(_app_dir(), f"{language}.json"),
        os.path.join(os.getcwd(), "locales", f"{language}.json"),
        os.path.join(os.getcwd(), f"{language}.json"),
    ):
        if path not in candidate_paths:
            candidate_paths.append(path)

    catalog = {}
    errors: list[str] = []
    for path in candidate_paths:
        if not os.path.exists(path):
            errors.append(f"missing:{path}")
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            catalog = data if isinstance(data, dict) else {}
            if catalog:
                _log_locale_event(language, f"loaded locale from {path}")
                break
            errors.append(f"invalid_json_shape:{path}")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")

    if not catalog:
        _log_locale_event(
            language,
            "failed to load locale "
            f"{language}; frozen={getattr(sys, 'frozen', False)}; "
            f"bundle_dir={_bundle_dir()}; app_dir={_app_dir()}; cwd={os.getcwd()}; "
            f"attempts={'; '.join(errors)}",
        )
    _LOCALE_CACHE[language] = catalog
    return catalog


def _saved_language() -> str:
    data = _load_app_config()
    value = data.get("language", "en")
    return value if value in _SUPPORTED_LANGUAGES else "en"


def _set_saved_language(language: str):
    if language not in _SUPPORTED_LANGUAGES:
        return
    data = _load_app_config()
    data["language"] = language
    _save_app_config(data)


def _set_current_language(language: str):
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = language if language in _SUPPORTED_LANGUAGES else "en"
    _load_locale_catalog("en")
    if _CURRENT_LANGUAGE != "en":
        _load_locale_catalog(_CURRENT_LANGUAGE)


def _current_language() -> str:
    return _CURRENT_LANGUAGE


def _tr(key: str, default: Optional[str] = None, **kwargs) -> str:
    text = _load_locale_catalog(_CURRENT_LANGUAGE).get(key)
    if text is None:
        text = _load_locale_catalog("en").get(key, default if default is not None else key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def _language_label(language: str) -> str:
    return _tr(_SUPPORTED_LANGUAGES.get(language, "language.english"))


def _font_size_offset_label(offset: int) -> str:
    return f"+{offset}pt" if offset > 0 else f"{offset}pt" if offset < 0 else _tr("common.default", default="default")


def _localized_room_display() -> dict[str, str]:
    return {
        "Floor1_Large": _tr("room.floor1_large", default="1F Left"),
        "Floor1_Small": _tr("room.floor1_small", default="1F Right"),
        "Floor2_Large": _tr("room.floor2_large", default="2F Right"),
        "Floor2_Small": _tr("room.floor2_small", default="2F Left"),
        "Attic": _tr("room.attic", default="Attic"),
    }


def _localized_status_abbrev() -> dict[str, str]:
    return {
        "In House": _tr("status.in_house"),
        "Adventure": _tr("status.adventure"),
        "Gone": _tr("status.gone"),
    }


def _refresh_localized_constants():
    # Mutate in-place so all modules holding references see the update
    ROOM_DISPLAY.clear()
    ROOM_DISPLAY.update(_localized_room_display())
    STATUS_ABBREV.clear()
    STATUS_ABBREV.update(_localized_status_abbrev())
    COLUMNS.clear()
    COLUMNS.extend([
        _tr("table.column.name"),
        _tr("table.column.age"),
        _tr("table.column.gender"),
        _tr("table.column.room"),
        _tr("table.column.status"),
        _tr("table.column.blacklist"),
        _tr("table.column.must_breed"),
        _tr("table.column.pinned"),
    ] + STAT_NAMES + [
        _tr("table.column.sum"),
        _tr("table.column.aggression"),
        _tr("table.column.libido"),
        _tr("table.column.inbred"),
        _tr("table.column.sexuality"),
        _tr("table.column.relations"),
        _tr("table.column.risk"),
        _tr("table.column.abilities"),
        _tr("table.column.mutations"),
        _tr("table.column.generation"),
        _tr("table.column.source"),
        _tr("table.column.adventure_ready", default="Adv Ready"),
        _tr("table.column.tags", default="Tags"),
    ])
