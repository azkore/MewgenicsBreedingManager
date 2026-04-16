"""Retry-with-backoff helper for transient save-file I/O failures.

The game rewrites the `.sav` atomically (temp file + rename).
`QFileSystemWatcher` fires on the rename but SQLite / LZ4 / low-level
file I/O can briefly see the file as locked, missing, or truncated.
Retrying a handful of times with short backoff turns those transient
failures into automatic recovery instead of a user-visible crash.
"""
import sqlite3
import time
from typing import Callable, TypeVar

T = TypeVar("T")


# Exceptions caused by the partial-write window — retryable.  Anything
# outside this tuple (TypeError, AttributeError, KeyError, …) indicates
# a real bug or a genuinely corrupted save, so propagate immediately
# rather than wasting ~350 ms re-running an expensive parse that will
# re-allocate hundreds of MB for nothing.
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    sqlite3.OperationalError,  # "database is locked", "disk I/O error", "unable to open"
    sqlite3.DatabaseError,     # malformed header / truncated file
    OSError,                   # file momentarily missing, NTFS rename blip
    EOFError,                  # truncated binary read mid-rename
)

_DEFAULT_DELAYS_MS = (50, 100, 200)


def retry_transient(func: Callable[[], T], delays_ms=_DEFAULT_DELAYS_MS) -> T:
    """Call `func()`, retrying up to len(delays_ms) times on transient I/O errors.

    Delays are applied *between* attempts, so len(delays_ms)+1 total attempts.
    Non-transient exceptions propagate on the first failure.
    """
    total_attempts = len(delays_ms) + 1
    for attempt in range(total_attempts):
        try:
            return func()
        except TRANSIENT_EXCEPTIONS:
            if attempt + 1 >= total_attempts:
                raise
            time.sleep(delays_ms[attempt] / 1000.0)
