"""Extract DefinedShape PNGs from a bundled ZIP or the game's GPAK archive.

At app startup, if the CatAssets/DefinedShapes directory is under-populated,
this module tries two sources in order:

  1. ``DefinedShapes.zip`` — a pre-built archive shipped alongside the app (~3 s).
  2. ``catparts.swf`` inside the game's GPAK — parsed and rendered via Qt (~25 s).

Once extracted, PNGs are cached on disk and never re-extracted.
"""
from __future__ import annotations

import logging
import math
import struct
import sys
import zipfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

from mewgenics.utils.ability_icons import (
    _BitReader,
    _gpak_entry_bytes,
    _parse_shape,
    _swf_rect_size,
)

logger = logging.getLogger("mewgenics.shapes")

_CATPARTS_SWF_NAME = "swfs/catparts.swf"
_CAT_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "CatAssets"
_DEFINED_SHAPES_DIR = _CAT_ASSETS_DIR / "DefinedShapes"

# Maximum pixel dimension for a single shape — skip anything absurd.
_MAX_SHAPE_DIM = 2000
# Minimum PNG count to consider the cache sufficiently populated.
_MIN_CACHED_SHAPES = 5000


def _iterate_swf_tags(data: bytes):
    """Yield (tag_code, payload_bytes) for every tag in a raw SWF stream."""
    if len(data) < 8:
        return
    sig = data[:3]
    if sig == b"CWS":
        import zlib
        data = data[:8] + zlib.decompress(data[8:])
    elif sig != b"FWS":
        return

    pos = 8 + _swf_rect_size(data, 8) + 4  # skip header + RECT + frame info
    while pos + 2 <= len(data):
        rec = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = rec >> 6
        length = rec & 0x3F
        if length == 0x3F:
            if pos + 4 > len(data):
                break
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if pos + length > len(data):
            break
        yield code, data[pos : pos + length]
        pos += length
        if code == 0:
            break


def _render_shape_to_png(code: int, payload: bytes) -> bytes | None:
    """Parse a DefinedShape payload and render it to PNG bytes at native size."""
    bounds, contours = _parse_shape(code, payload)
    if not contours:
        return None
    if not bounds.isValid() or bounds.width() <= 0 or bounds.height() <= 0:
        return None

    w = int(bounds.width()) + 1
    h = int(bounds.height()) + 1
    if w <= 0 or h <= 0 or w > _MAX_SHAPE_DIM or h > _MAX_SHAPE_DIM:
        return None

    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    # Map shape coordinate space so bounds.topLeft() sits at canvas origin.
    painter.translate(-bounds.left(), -bounds.top())

    for color, path in contours:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)

    painter.end()

    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(buf.data())


def extract_catparts_shapes(gpak_path: str | None, output_dir: Path | None = None) -> int:
    """Extract all DefinedShape PNGs from catparts.swf to *output_dir*.

    Skips shapes that already have a corresponding PNG on disk.
    Returns the number of newly-written files.
    """
    if output_dir is None:
        output_dir = _DEFINED_SHAPES_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not gpak_path:
        logger.warning("No GPAK path — cannot extract DefinedShapes")
        return 0

    data = _gpak_entry_bytes(gpak_path, _CATPARTS_SWF_NAME)
    if data is None:
        logger.warning("Could not read %s from GPAK at %s", _CATPARTS_SWF_NAME, gpak_path)
        return 0

    # Collect every DefinedShape tag payload keyed by character_id.
    shape_defs: dict[int, tuple[int, bytes]] = {}
    for code, payload in _iterate_swf_tags(data):
        if code in (2, 22, 32, 83) and len(payload) >= 2:
            char_id = struct.unpack_from("<H", payload, 0)[0]
            shape_defs[char_id] = (code, payload)

    logger.info("catparts.swf contains %d DefinedShape tags", len(shape_defs))

    written = 0
    skipped = 0
    errors = 0
    for char_id, (code, payload) in shape_defs.items():
        png_path = output_dir / f"{char_id}.png"
        if png_path.exists():
            skipped += 1
            continue
        try:
            png_bytes = _render_shape_to_png(code, payload)
        except Exception:
            logger.debug("Failed to parse/render shape %d", char_id, exc_info=True)
            errors += 1
            continue
        if png_bytes is None:
            continue
        png_path.write_bytes(png_bytes)
        written += 1

    logger.info(
        "DefinedShapes extraction: %d written, %d already cached, %d errors",
        written, skipped, errors,
    )
    return written


def _find_shapes_zip() -> Path | None:
    """Locate DefinedShapes.zip in candidate directories."""
    candidates = [
        _CAT_ASSETS_DIR / "DefinedShapes.zip",
    ]
    # In a frozen PyInstaller build, also check the bundle directory.
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", ""))
        candidates.append(bundle / "CatAssets" / "DefinedShapes.zip")
    for p in candidates:
        if p.is_file():
            return p
    return None


def _extract_from_zip(zip_path: Path, output_dir: Path) -> int:
    """Extract PNGs from a DefinedShapes.zip archive.

    Skips files that already exist on disk.  Returns newly-written count.
    """
    written = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".png"):
                continue
            dest = output_dir / info.filename
            if dest.exists():
                continue
            dest.write_bytes(zf.read(info.filename))
            written += 1
    return written


def ensure_defined_shapes(gpak_path: str | None) -> None:
    """Extract shapes if the cache directory is empty or missing many files.

    Intended to be called once during app startup after QApplication exists.
    Tries the bundled ZIP first (~3 s), then falls back to GPAK extraction (~25 s).
    """
    output_dir = _DEFINED_SHAPES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sum(1 for f in output_dir.iterdir() if f.suffix == ".png")
    if existing >= _MIN_CACHED_SHAPES:
        logger.debug("DefinedShapes cache has %d PNGs — skipping extraction", existing)
        return

    logger.info("DefinedShapes cache has only %d PNGs — looking for sources", existing)

    # Try 1: Extract from bundled ZIP (fast).
    zip_path = _find_shapes_zip()
    if zip_path is not None:
        logger.info("Extracting shapes from %s", zip_path)
        written = _extract_from_zip(zip_path, output_dir)
        logger.info("ZIP extraction: %d new PNGs written", written)
        # Re-check — if the zip was sufficient, we're done.
        existing += written
        if existing >= _MIN_CACHED_SHAPES:
            return

    # Try 2: Render from GPAK (slower, requires the game).
    logger.info("Falling back to GPAK extraction")
    extract_catparts_shapes(gpak_path, output_dir)
