"""Tests for localization module and locale file integrity."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from mewgenics.utils.localization import _tr, _LOCALE_CACHE, _set_current_language

LOCALES_DIR = _proj_root / "locales"
LOCALE_FILES = list(LOCALES_DIR.glob("*.json"))


class TestTrFunction:
    def setup_method(self):
        _LOCALE_CACHE.clear()
        _set_current_language("en")

    def test_returns_default_when_key_missing(self):
        result = _tr("nonexistent.key.xyz", default="fallback text")
        assert result == "fallback text"

    def test_returns_key_when_no_default(self):
        result = _tr("nonexistent.key.xyz")
        assert result == "nonexistent.key.xyz"

    def test_format_kwargs(self):
        # Use a key we know exists in en.json
        result = _tr("app.title_with_save", name="TestSave")
        assert "TestSave" in result

    def test_returns_known_key(self):
        result = _tr("app.title")
        assert result == "Mewgenics Breeding Manager"


class TestLocaleFiles:
    def test_all_locale_files_are_valid_json(self):
        assert len(LOCALE_FILES) >= 4, f"Expected at least 4 locale files, found {len(LOCALE_FILES)}"
        for path in LOCALE_FILES:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{path.name} should contain a JSON object"

    def test_en_keys_superset_of_other_locales(self):
        en_path = LOCALES_DIR / "en.json"
        with open(en_path, "r", encoding="utf-8") as f:
            en_keys = set(json.load(f).keys())

        for path in LOCALE_FILES:
            if path.name == "en.json":
                continue
            with open(path, "r", encoding="utf-8") as f:
                other_keys = set(json.load(f).keys())
            extra = other_keys - en_keys
            assert not extra, (
                f"{path.name} has keys not in en.json: {sorted(extra)[:10]}"
            )

    def test_no_empty_values_in_en(self):
        en_path = LOCALES_DIR / "en.json"
        with open(en_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        empty_keys = [k for k, v in data.items() if not v.strip()]
        assert not empty_keys, f"en.json has empty values for: {empty_keys[:10]}"
