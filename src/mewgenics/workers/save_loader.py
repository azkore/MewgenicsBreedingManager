"""SaveLoadWorker: parses a save file off the main thread."""
from PySide6.QtCore import QThread, Signal

from save_parser import parse_save
from mewgenics.utils.cat_persistence import (
    _load_blacklist, _load_must_breed, _load_pinned, _load_tags,
    _load_not_adventured,
)
from mewgenics.utils.calibration import _load_gender_overrides, _apply_calibration
from mewgenics.utils.retry import retry_transient, TRANSIENT_EXCEPTIONS


class SaveLoadWorker(QThread):
    """Parses a save file off the main thread so the UI stays responsive."""
    status = Signal(str)  # status text updates
    finished_load = Signal(object)  # emits dict with parsed results
    # (error_repr, is_transient) — is_transient distinguishes partial-write
    # races (worth a self-heal retry) from real errors (don't retry-loop).
    failed = Signal(str, bool)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            self.status.emit("Parsing save file…")
            # retry_transient recovers from the partial-write window the
            # game briefly opens when it renames its temp save over the
            # real file.  Non-transient errors (corrupt saves, missing
            # file, etc.) propagate immediately.
            save = retry_transient(lambda: parse_save(self._path))
            cats, errors, unlocked_house_rooms = save
            self.status.emit("Loading blacklist & overrides…")
            _load_blacklist(self._path, cats)
            _load_must_breed(self._path, cats)
            _load_pinned(self._path, cats)
            _load_tags(self._path, cats)
            _load_not_adventured(self._path, cats)
            applied_overrides, override_rows = _load_gender_overrides(self._path, cats)
            cal_explicit, cal_token, cal_rows = _apply_calibration(self._path, cats)
            self.finished_load.emit({
                "cats": cats,
                "errors": errors,
                "unlocked_house_rooms": unlocked_house_rooms,
                "accessible_cats": save.accessible_cats,
                "furniture": save.furniture,
                "furniture_by_room": save.furniture_by_room,
                "pedigree_coi_memos": save.pedigree_coi_memos,
                "applied_overrides": applied_overrides,
                "override_rows": override_rows,
                "cal_explicit": cal_explicit,
                "cal_token": cal_token,
                "cal_rows": cal_rows,
            })
        except Exception as exc:  # noqa: BLE001 — last line of defence before QThread dies silently
            # Without this, an unhandled exception would kill the QThread,
            # `finished_load` would never fire, the loading overlay would
            # stay up, and `_save_load_worker` on MainWindow would remain
            # non-None — so every subsequent file-change event would
            # cascade into the old terminate() path.
            self.failed.emit(repr(exc), isinstance(exc, TRANSIENT_EXCEPTIONS))
