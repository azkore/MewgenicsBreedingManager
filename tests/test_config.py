"""Tests for config module."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from mewgenics.utils.config import (
    _load_app_config,
    _save_app_config,
    _candidate_gpak_paths,
    _coerce_int,
    _coerce_float,
    _coerce_bool,
)
from mewgenics.utils.paths import APP_CONFIG_PATH


class TestLoadSaveConfig:
    def test_returns_empty_dict_on_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mewgenics.utils.config.APP_CONFIG_PATH",
            str(tmp_path / "nonexistent.json"),
        )
        assert _load_app_config() == {}

    def test_round_trips_data(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "test_config.json"
        monkeypatch.setattr("mewgenics.utils.config.APP_CONFIG_PATH", str(cfg_path))
        monkeypatch.setattr("mewgenics.utils.config.APPDATA_CONFIG_DIR", str(tmp_path))

        test_data = {"language": "ru", "zoom_percent": 125}
        _save_app_config(test_data)

        loaded = _load_app_config()
        assert loaded["language"] == "ru"
        assert loaded["zoom_percent"] == 125

    def test_handles_corrupt_json(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "bad_config.json"
        cfg_path.write_text("{invalid json", encoding="utf-8")
        monkeypatch.setattr("mewgenics.utils.config.APP_CONFIG_PATH", str(cfg_path))
        assert _load_app_config() == {}

    def test_handles_non_dict_json(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "array_config.json"
        cfg_path.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setattr("mewgenics.utils.config.APP_CONFIG_PATH", str(cfg_path))
        assert _load_app_config() == {}


class TestCandidateGpakPaths:
    def test_returns_list_of_strings(self):
        result = _candidate_gpak_paths()
        assert isinstance(result, list)
        assert all(isinstance(p, str) for p in result)

    def test_no_duplicates(self):
        result = _candidate_gpak_paths()
        # Paths are deduplicated by normcase/normpath
        assert len(result) == len(set(result))


class TestCoercionHelpers:
    def test_coerce_int_valid(self):
        assert _coerce_int("42", 0) == 42
        assert _coerce_int(3.7, 0) == 3

    def test_coerce_int_invalid(self):
        assert _coerce_int("abc", 10) == 10
        assert _coerce_int(None, 5) == 5

    def test_coerce_int_clamps(self):
        assert _coerce_int(200, 0, min_value=0, max_value=100) == 100
        assert _coerce_int(-5, 0, min_value=0) == 0

    def test_coerce_float_valid(self):
        assert _coerce_float("3.14", 0.0) == pytest.approx(3.14)

    def test_coerce_float_invalid(self):
        assert _coerce_float("xyz", 1.5) == 1.5

    def test_coerce_bool(self):
        assert _coerce_bool(True) is True
        assert _coerce_bool(False) is False
        assert _coerce_bool("yes") is True
        assert _coerce_bool("no") is False
        assert _coerce_bool(None, default=True) is True
