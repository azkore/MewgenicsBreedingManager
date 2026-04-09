"""Tests for shape_extractor module."""
import struct
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from mewgenics.utils.shape_extractor import (
    _iterate_swf_tags,
    _extract_from_zip,
    _find_shapes_zip,
    _DEFINED_SHAPES_DIR,
    _MIN_CACHED_SHAPES,
    ensure_defined_shapes,
)


def _make_minimal_fws() -> bytes:
    """Build a minimal valid FWS (uncompressed SWF) with one End tag."""
    # FWS signature + version 10 + file length (filled later)
    header = bytearray(b"FWS\x0a\x00\x00\x00\x00")
    # Minimal RECT: Nbits=0 -> 5 zero bits, padded to 1 byte
    rect = bytes([0b00000_000])
    # Frame rate (2 bytes) + frame count (2 bytes)
    frame_info = b"\x00\x01\x01\x00"
    # End tag: tag code 0, length 0 -> record header 0x0000
    end_tag = struct.pack("<H", 0)
    body = rect + frame_info + end_tag
    # File length = 8 (header) + body
    total = 8 + len(body)
    struct.pack_into("<I", header, 4, total)
    return bytes(header) + body


def _make_fws_with_shape(char_id: int = 42) -> bytes:
    """Build a FWS with one DefinedShape (tag code 2) containing *char_id*."""
    header = bytearray(b"FWS\x0a\x00\x00\x00\x00")
    rect = bytes([0b00000_000])
    frame_info = b"\x00\x01\x01\x00"

    # DefinedShape payload: just the character ID (2 bytes) — will be too
    # short for _parse_shape to produce real contours, but enough to test
    # iteration picks it up.
    payload = struct.pack("<H", char_id)
    tag_code = 2
    rec = (tag_code << 6) | (len(payload) & 0x3F)
    shape_tag = struct.pack("<H", rec) + payload

    end_tag = struct.pack("<H", 0)
    body = rect + frame_info + shape_tag + end_tag
    total = 8 + len(body)
    struct.pack_into("<I", header, 4, total)
    return bytes(header) + body


class TestIterateSwfTags:
    def test_empty_data(self):
        assert list(_iterate_swf_tags(b"")) == []

    def test_bad_signature(self):
        assert list(_iterate_swf_tags(b"XYZ\x0a" + b"\x00" * 20)) == []

    def test_minimal_fws_yields_end_tag(self):
        tags = list(_iterate_swf_tags(_make_minimal_fws()))
        assert len(tags) == 1
        code, payload = tags[0]
        assert code == 0  # End tag

    def test_fws_with_shape_tag(self):
        data = _make_fws_with_shape(char_id=99)
        tags = list(_iterate_swf_tags(data))
        # Should have DefinedShape + End
        codes = [t[0] for t in tags]
        assert 2 in codes
        # The shape payload should start with the char_id
        for code, payload in tags:
            if code == 2:
                cid = struct.unpack_from("<H", payload, 0)[0]
                assert cid == 99


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
        ensure_defined_shapes(None)
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

        ensure_defined_shapes(None)
        extracted = sum(1 for f in shapes_dir.iterdir() if f.suffix == ".png")
        assert extracted >= _MIN_CACHED_SHAPES
