#!/usr/bin/env python3
"""Profile app startup to identify bottlenecks.

Run from the project root:
    python tools/profile_startup.py [path/to/save.sav]

Measures wall-clock time for each startup phase:
  1. Python interpreter + initial imports
  2. mewgenics package init (game data, locale, tags, thresholds)
  3. QApplication + palette setup
  4. DefinedShapes extraction check
  5. MainWindow construction (UI build, menus, models)
  6. Save file loading + parsing
  7. Breeding cache computation

Exits automatically after the breeding cache finishes (or after 60s timeout).
"""
from __future__ import annotations

import os
import sys
import time

# Record the very first timestamp before any imports
_T0 = time.perf_counter()

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

_timings: list[tuple[str, float, float]] = []


def _mark(label: str, start: float) -> float:
    end = time.perf_counter()
    _timings.append((label, start, end))
    return end


def _report():
    print("\n" + "=" * 64)
    print("  STARTUP PROFILE")
    print("=" * 64)
    total = _timings[-1][2] - _timings[0][1] if _timings else 0
    for label, start, end in _timings:
        elapsed = end - start
        pct = (elapsed / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {elapsed:6.3f}s  {pct:5.1f}%  {bar:25s}  {label}")
    print("-" * 64)
    print(f"  {total:6.3f}s  TOTAL")
    print("=" * 64)


def main():
    t = _T0

    # Phase 1: Core imports
    t = _mark("Python startup → script begin", t)

    import importlib
    t1 = time.perf_counter()
    import save_parser  # noqa: F401
    import breeding  # noqa: F401
    t = _mark("Import save_parser + breeding", t1)

    t1 = time.perf_counter()
    import mewgenics  # noqa: F401  — triggers __init__.py (game data, locale, tags, thresholds)
    t = _mark("mewgenics.__init__ (game data, locale, tags, thresholds)", t1)

    t1 = time.perf_counter()
    from PySide6.QtWidgets import QApplication, QDialog
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtCore import QTimer
    t = _mark("Import PySide6", t1)

    # Phase 2: QApplication
    t1 = time.perf_counter()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(13,  13,  28))
    pal.setColor(QPalette.WindowText,      QColor(220, 220, 230))
    pal.setColor(QPalette.Base,            QColor(18,  18,  36))
    pal.setColor(QPalette.AlternateBase,   QColor(20,  20,  40))
    pal.setColor(QPalette.Text,            QColor(220, 220, 230))
    pal.setColor(QPalette.Button,          QColor(22,  22,  46))
    pal.setColor(QPalette.ButtonText,      QColor(200, 200, 210))
    pal.setColor(QPalette.Highlight,       QColor(30,  48, 100))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipBase,     QColor(20,  20,  40))
    pal.setColor(QPalette.ToolTipText,     QColor(220, 220, 230))
    app.setPalette(pal)
    t = _mark("QApplication + palette", t1)

    # Phase 3: DefinedShapes
    t1 = time.perf_counter()
    from mewgenics.utils.shape_extractor import ensure_defined_shapes
    ensure_defined_shapes()
    t = _mark("ensure_defined_shapes (ZIP check/extract)", t1)

    # Phase 4: MainWindow construction
    t1 = time.perf_counter()
    from mewgenics.main_window import MainWindow
    t = _mark("Import MainWindow module", t1)

    # Determine save file
    save_path = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        save_path = sys.argv[1]
    else:
        from mewgenics.utils.config import _saved_default_save
        default = _saved_default_save()
        if default and os.path.isfile(default):
            save_path = default

    if not save_path:
        print("\nNo save file found. Pass one as argument or set a default in the app.")
        print("Profiling without save loading.\n")

    t1 = time.perf_counter()
    # Create MainWindow WITHOUT auto-loading (we'll load manually to measure)
    win = MainWindow(initial_save=None, use_saved_default=False)
    t = _mark("MainWindow.__init__ (UI build, no save)", t1)

    if save_path:
        # Phase 5: Save loading
        t1 = time.perf_counter()
        # Monkey-patch to capture when save loading completes
        _orig_on_save_loaded = win._on_save_loaded
        _save_load_end = [None]

        def _patched_on_save_loaded(*args, **kwargs):
            result = _orig_on_save_loaded(*args, **kwargs)
            _save_load_end[0] = time.perf_counter()
            return result

        win._on_save_loaded = _patched_on_save_loaded

        # Monkey-patch breeding cache completion
        _orig_cache_done = win._on_cache_done
        _cache_done_time = [None]

        def _patched_cache_done(*args, **kwargs):
            result = _orig_cache_done(*args, **kwargs)
            _cache_done_time[0] = time.perf_counter()
            # Report and exit after cache completes
            if _save_load_end[0]:
                _mark("Save parse + _on_save_loaded", t1)
                if _cache_done_time[0] and _save_load_end[0]:
                    _mark("Breeding cache computation", _save_load_end[0])
            _report()
            app.quit()
            return result

        win._on_cache_done = _patched_cache_done

        win.load_save(save_path)
        win.show()

        # Safety timeout — exit after 60s even if cache never finishes
        QTimer.singleShot(60000, lambda: (_report(), app.quit()))

        app.exec()
    else:
        _report()


if __name__ == "__main__":
    main()
