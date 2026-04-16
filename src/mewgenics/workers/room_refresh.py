"""QuickRoomRefreshWorker: fast room assignment refresh without full parse."""
import sqlite3

from PySide6.QtCore import QThread, Signal

from save_parser import _get_house_info, _get_adventure_keys
from mewgenics.utils.retry import retry_transient


class QuickRoomRefreshWorker(QThread):
    """Fast path: re-reads only house_state/adventure_state to update room assignments.

    If the set of cat keys in the DB has changed (birth/death), emits needs_full_reload
    instead so the caller can fall back to a full SaveLoadWorker parse.

    A *generation* token is passed through and re-emitted alongside the
    result.  MainWindow compares that token against its current generation
    to discard signals from superseded workers — preventing a stale
    room_patch from clobbering freshly-loaded state.
    """
    # (generation, patch dict)  db_key → (room, status)
    room_patch = Signal(int, object)
    needs_full_reload = Signal(int)

    def __init__(self, path: str, expected_keys: set, generation: int = 0, parent=None):
        super().__init__(parent)
        self._path = path
        self._expected_keys = expected_keys
        self._generation = generation

    def _read_state(self):
        """Open the save read-only and return (live_keys, house, adv).

        Raises the underlying sqlite3 exception if the file can't be opened
        or queried — retry_transient handles the partial-write window.
        """
        conn = None
        try:
            conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
            live_keys = {row[0] for row in conn.execute("SELECT key FROM cats").fetchall()}
            house = _get_house_info(conn)
            adv = _get_adventure_keys(conn)
            return live_keys, house, adv
        finally:
            if conn is not None:
                # close() can raise if the connection is already broken
                # by the error we're unwinding — swallow so we don't mask
                # the real exception.
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def run(self):
        try:
            live_keys, house, adv = retry_transient(self._read_state)
            if live_keys != self._expected_keys:
                self.needs_full_reload.emit(self._generation)
                return
            patch: dict[int, tuple[str, str]] = {}
            for key in live_keys:
                if key in adv:
                    patch[key] = ("Adventure", "Adventure")
                elif key in house:
                    patch[key] = (house[key], "In House")
                else:
                    patch[key] = ("", "Gone")
            self.room_patch.emit(self._generation, patch)
        except Exception:
            self.needs_full_reload.emit(self._generation)
