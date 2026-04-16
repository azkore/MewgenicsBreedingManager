"""Crash logging and unhandled exception capture.

Frozen Windows builds run with ``console=False`` in the PyInstaller spec,
which means ``stdout``/``stderr`` are discarded and uncaught exceptions
vanish silently. This module installs a rotating file log and global
exception hooks so crashes can be diagnosed after the fact.

Log file lives at ``%APPDATA%/MewgenicsBreedingManager/logs/mewgenics.log``.
"""
import logging
import logging.handlers
import os
import sys
import threading
import traceback
from typing import Callable, Optional

from mewgenics.utils.paths import APPDATA_CONFIG_DIR, APP_VERSION


LOG_DIR = os.path.join(APPDATA_CONFIG_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "mewgenics.log")

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
_BACKUP_COUNT = 3              # keep mewgenics.log + .1 + .2 + .3

_setup_done = False


def setup_logging(level_name: Optional[str] = None) -> str:
    """Install rotating file handler + stream handler on the root logger.

    Returns the absolute path to the active log file. Safe to call more
    than once — subsequent calls are no-ops.
    """
    global _setup_done
    if _setup_done:
        return LOG_FILE

    level_name = (level_name or os.environ.get("MEWGENICS_LOG_LEVEL", "INFO")).strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers a prior basicConfig() call may have installed so we
    # don't double-log every line.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
    except Exception:
        # If file logging fails (permissions, disk full), fall through to
        # stream-only logging. Don't crash the app on startup.
        pass

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)

    logger = logging.getLogger("mewgenics")
    logger.info("=" * 72)
    logger.info("Mewgenics Breeding Manager %s starting (pid=%d)", APP_VERSION, os.getpid())
    logger.info("Log file: %s", LOG_FILE)

    _setup_done = True
    return LOG_FILE


def install_excepthooks(dialog_parent_getter: Optional[Callable] = None) -> None:
    """Install ``sys.excepthook`` and ``threading.excepthook``.

    Unhandled exceptions on any thread will be logged with a full traceback
    and, for the main thread, a Qt message box will be shown pointing the
    user at the log file.

    ``dialog_parent_getter`` is an optional callable returning the active
    QWidget (or ``None``) to use as parent for the crash dialog. Using a
    getter instead of a widget reference lets the hook be installed before
    the main window exists.
    """
    logger = logging.getLogger("mewgenics.crash")

    # ── Main-thread hook ──────────────────────────────────────────────
    def _handle_main(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            # Preserve Ctrl-C behavior in dev
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Unhandled exception on main thread:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        _show_crash_dialog(exc_type, exc_value, dialog_parent_getter)

    sys.excepthook = _handle_main

    # ── Background thread hook (Python 3.8+) ──────────────────────────
    def _handle_thread(args: threading.ExceptHookArgs):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Unhandled exception on thread %r:\n%s",
            getattr(args.thread, "name", "?"),
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )
        # Don't pop a dialog for background-thread crashes — they may be
        # transient worker failures and spamming dialogs would be worse
        # than the bug. The log file captures them.

    threading.excepthook = _handle_thread

    # ── Qt message handler ────────────────────────────────────────────
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return

    qt_logger = logging.getLogger("mewgenics.qt")
    _qt_level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _qt_handler(msg_type, context, message):
        level = _qt_level_map.get(msg_type, logging.INFO)
        location = ""
        if context is not None:
            file_name = getattr(context, "file", None) or ""
            line_no = getattr(context, "line", 0) or 0
            if file_name:
                location = f" ({file_name}:{line_no})"
        qt_logger.log(level, "%s%s", message, location)

    try:
        qInstallMessageHandler(_qt_handler)
    except Exception:
        pass


def _show_crash_dialog(exc_type, exc_value, dialog_parent_getter: Optional[Callable]) -> None:
    """Show a modal crash dialog pointing at the log file.

    Only attempted if a QApplication already exists — otherwise the crash
    happened before Qt was ready and we just exit.
    """
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    if QApplication.instance() is None:
        return

    parent = None
    if dialog_parent_getter is not None:
        try:
            parent = dialog_parent_getter()
        except Exception:
            parent = None

    try:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Mewgenics Breeding Manager — Unexpected Error")
        box.setText(
            f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}"
        )
        box.setInformativeText(
            "A full crash report has been written to:\n\n"
            f"{LOG_FILE}\n\n"
            "Please attach this file when reporting the bug."
        )
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
    except Exception:
        # Swallow secondary errors from the dialog itself — the log is
        # already written at this point, which is what matters.
        pass
