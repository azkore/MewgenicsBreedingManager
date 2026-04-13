"""Dev-only: rebuild src/CatAssets/DefinedShapes.zip from the game's GPAK.

Run this when the game ships new cat parts (catparts.swf changes) so that
pre-rendered DefinedShape PNGs stay in sync with the game.

Requires:
  - Java 8+ on PATH (or pass --java PATH)
  - ffdec.jar from https://github.com/jindrapetrik/jpexs-decompiler/releases
    (pass path via --ffdec, or drop ffdec.jar next to this script)

Usage:
    python tools/rebuild_defined_shapes.py \\
        --gpak "/path/to/Mewgenics/resources.gpak" \\
        --ffdec "/path/to/ffdec.jar"

The script:
  1. Extracts ``swfs/catparts.swf`` from the GPAK archive.
  2. Invokes ``java -jar ffdec.jar -format shape:png -export shape``.
  3. Re-zips the 10k+ PNGs into ``src/CatAssets/DefinedShapes.zip``.

The Qt-based SWF parser previously used as a runtime fallback was removed
because it produced incorrect output (missing outlines, wrong chroma) for
~35% of shapes. The pre-rendered FFDEC PNGs are now the sole source.
"""
from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ZIP = REPO_ROOT / "src" / "CatAssets" / "DefinedShapes.zip"


def gpak_entry_bytes(gpak_path: Path, target_name: str) -> bytes | None:
    """Read a single file out of the game's GPAK archive."""
    with open(gpak_path, "rb") as f:
        count = struct.unpack("<I", f.read(4))[0]
        entries = []
        for _ in range(count):
            name_len = struct.unpack("<H", f.read(2))[0]
            name = f.read(name_len).decode("utf-8", errors="replace")
            size = struct.unpack("<I", f.read(4))[0]
            entries.append((name, size))
        dir_end = f.tell()
        offset = dir_end
        for name, size in entries:
            if name == target_name:
                f.seek(offset)
                return f.read(size)
            offset += size
    return None


def run_ffdec(java: str, ffdec_jar: Path, swf: Path, out_dir: Path) -> None:
    cmd = [
        java, "-jar", str(ffdec_jar),
        "-format", "shape:png",
        "-export", "shape", str(out_dir), str(swf),
    ]
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def build_zip(pngs_dir: Path, out_zip: Path) -> int:
    pngs = sorted(pngs_dir.glob("*.png"), key=lambda p: int(p.stem))
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in pngs:
            zf.write(p, arcname=p.name)
    return len(pngs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gpak", required=True, type=Path, help="Path to Mewgenics resources.gpak")
    ap.add_argument("--ffdec", type=Path, default=Path(__file__).parent / "ffdec.jar",
                    help="Path to ffdec.jar (default: tools/ffdec.jar)")
    ap.add_argument("--java", default="java", help="Java executable (default: 'java' on PATH)")
    args = ap.parse_args()

    if not args.gpak.is_file():
        print(f"ERROR: GPAK not found: {args.gpak}", file=sys.stderr)
        return 1
    if not args.ffdec.is_file():
        print(f"ERROR: ffdec.jar not found: {args.ffdec}", file=sys.stderr)
        print("Download from https://github.com/jindrapetrik/jpexs-decompiler/releases", file=sys.stderr)
        return 1
    if shutil.which(args.java) is None and not Path(args.java).is_file():
        print(f"ERROR: java not found: {args.java}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="defshape_rebuild_") as tmp:
        tmp_path = Path(tmp)
        swf_path = tmp_path / "catparts.swf"
        shapes_dir = tmp_path / "shapes"
        shapes_dir.mkdir()

        print(f"Extracting swfs/catparts.swf from {args.gpak}")
        data = gpak_entry_bytes(args.gpak, "swfs/catparts.swf")
        if data is None:
            print("ERROR: swfs/catparts.swf not present in GPAK", file=sys.stderr)
            return 1
        swf_path.write_bytes(data)
        print(f"  wrote {len(data)} bytes")

        print(f"Running FFDEC shape export")
        run_ffdec(args.java, args.ffdec, swf_path, shapes_dir)

        n = build_zip(shapes_dir, OUT_ZIP)
        print(f"Wrote {OUT_ZIP} ({n} shapes, {OUT_ZIP.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
