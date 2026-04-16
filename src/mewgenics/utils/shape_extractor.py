"""Extract DefinedShape PNGs from the bundled ``DefinedShapes.zip``.

At app startup, if the shapes cache directory is under-populated, this
module unpacks ``src/CatAssets/DefinedShapes.zip`` into the cache. That
ZIP is the sole source of truth — it is built offline with JPEXS FFDEC
(see ``tools/rebuild_defined_shapes.py``) and committed to git.

Once extracted, PNGs are cached on disk and never re-extracted.

Historical note: earlier versions also shipped a Qt/PySide-based SWF
shape parser that could rasterize shapes from ``catparts.swf`` inside the
game's GPAK as a fallback. That parser silently produced incorrect output
for ~35% of shapes (missing outlines, wrong fill handling), so it was
removed in favor of a single authoritative pre-rendered archive.
"""
from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

from mewgenics.utils.paths import APPDATA_CONFIG_DIR

logger = logging.getLogger("mewgenics.shapes")

_CAT_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "CatAssets"


def defined_shapes_dir() -> Path:
    """Return the persistent cache directory for extracted DefinedShape PNGs.

    In frozen PyInstaller builds the cache MUST live outside the bundle,
    because onefile mode wipes ``sys._MEIPASS`` between runs. A previous
    release bundled 6,894 small PNGs directly into the exe; the
    bootloader's small-file extraction on every launch cost ~15 s of
    startup time on Windows. Writing the cache to ``%APPDATA%`` means the
    ZIP is unpacked exactly once per install.

    In dev mode the cache lives next to the source at
    ``src/CatAssets/DefinedShapes`` so developers can inspect individual
    PNGs without installing the app.
    """
    if getattr(sys, "frozen", False):
        return Path(APPDATA_CONFIG_DIR) / "CatAssets" / "DefinedShapes"
    return _CAT_ASSETS_DIR / "DefinedShapes"


_DEFINED_SHAPES_DIR = defined_shapes_dir()

# Minimum PNG count to consider the cache sufficiently populated.
_MIN_CACHED_SHAPES = 5000


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


def _extract_from_zip(zip_path: Path, output_dir: Path,
                      progress_callback=None) -> int:
    """Extract PNGs from a DefinedShapes.zip archive.

    Skips files that already exist on disk.  Returns newly-written count.
    *progress_callback*, if provided, is called with ``(current, total)``
    periodically during extraction.
    """
    written = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        png_entries = [i for i in zf.infolist() if i.filename.endswith(".png")]
        total = len(png_entries)
        for idx, info in enumerate(png_entries):
            dest = output_dir / info.filename
            if not dest.exists():
                dest.write_bytes(zf.read(info.filename))
                written += 1
            if progress_callback and idx % 200 == 0:
                progress_callback(idx, total)
        if progress_callback:
            progress_callback(total, total)
    return written


def ensure_defined_shapes(progress_callback=None) -> None:
    """Extract shapes from the bundled ZIP if the cache is empty or sparse.

    Intended to be called once during app startup after QApplication exists.
    The ZIP is the only source — if it is missing, shapes will not render.

    *progress_callback*, if provided, is called with ``(current, total)``
    during extraction so the caller can update a splash screen.
    """
    output_dir = _DEFINED_SHAPES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sum(1 for f in output_dir.iterdir() if f.suffix == ".png")
    if existing >= _MIN_CACHED_SHAPES:
        logger.debug("DefinedShapes cache has %d PNGs — skipping extraction", existing)
        return

    logger.info("DefinedShapes cache has only %d PNGs — extracting from ZIP", existing)

    zip_path = _find_shapes_zip()
    if zip_path is None:
        logger.error(
            "DefinedShapes.zip not found — cat sprites will not render. "
            "Expected at %s",
            _CAT_ASSETS_DIR / "DefinedShapes.zip",
        )
        return

    logger.info("Extracting shapes from %s", zip_path)
    written = _extract_from_zip(zip_path, output_dir,
                                progress_callback=progress_callback)
    logger.info("ZIP extraction: %d new PNGs written", written)
