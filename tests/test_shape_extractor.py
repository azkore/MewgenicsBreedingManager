"""Tests for shape_extractor module."""
import sys
import zipfile
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from mewgenics.utils.shape_extractor import (
    _extract_from_zip,
    _find_shapes_zip,
    _MIN_CACHED_SHAPES,
    ensure_defined_shapes,
)


class TestExtractFromZip:
    def test_extracts_pngs(self, tmp_path):
        zip_path = tmp_path / "shapes.zip"
        out_dir = tmp_path / "output"
        out_dir.mkdir()

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("1.png", b"fake-png-1")
            zf.writestr("2.png", b"fake-png-2")
            zf.writestr("readme.txt", b"not a png")

        written = _extract_from_zip(zip_path, out_dir)
        assert written == 2
        assert (out_dir / "1.png").read_bytes() == b"fake-png-1"
        assert (out_dir / "2.png").read_bytes() == b"fake-png-2"
        assert not (out_dir / "readme.txt").exists()

    def test_skips_existing(self, tmp_path):
        zip_path = tmp_path / "shapes.zip"
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "1.png").write_bytes(b"already-here")

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("1.png", b"new-data")
            zf.writestr("2.png", b"new-data-2")

        written = _extract_from_zip(zip_path, out_dir)
        assert written == 1
        # Original should be untouched
        assert (out_dir / "1.png").read_bytes() == b"already-here"


class TestFindShapesZip:
    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.setattr(
            "mewgenics.utils.shape_extractor._CAT_ASSETS_DIR",
            Path("/nonexistent/path"),
        )
        assert _find_shapes_zip() is None


class TestEnsureDefinedShapes:
    def test_skips_when_cache_full(self, tmp_path, monkeypatch):
        """When >= _MIN_CACHED_SHAPES PNGs exist, no extraction happens."""
        shapes_dir = tmp_path / "DefinedShapes"
        shapes_dir.mkdir()
        for i in range(_MIN_CACHED_SHAPES):
            (shapes_dir / f"{i}.png").write_bytes(b"x")

        monkeypatch.setattr(
            "mewgenics.utils.shape_extractor._DEFINED_SHAPES_DIR", shapes_dir
        )
        # Should return without trying anything
        ensure_defined_shapes()
        # No crash = success

    def test_extracts_from_zip_when_cache_empty(self, tmp_path, monkeypatch):
        shapes_dir = tmp_path / "DefinedShapes"
        shapes_dir.mkdir()
        monkeypatch.setattr(
            "mewgenics.utils.shape_extractor._DEFINED_SHAPES_DIR", shapes_dir
        )

        # Create a zip with enough PNGs
        zip_path = tmp_path / "CatAssets" / "DefinedShapes.zip"
        zip_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(_MIN_CACHED_SHAPES + 10):
                zf.writestr(f"{i}.png", b"x")

        monkeypatch.setattr(
            "mewgenics.utils.shape_extractor._CAT_ASSETS_DIR",
            tmp_path / "CatAssets",
        )

        ensure_defined_shapes()
        extracted = sum(1 for f in shapes_dir.iterdir() if f.suffix == ".png")
        assert extracted >= _MIN_CACHED_SHAPES
