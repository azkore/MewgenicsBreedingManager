"""SaveLoadWorker: parses a save file off the main thread."""
from PySide6.QtCore import QThread, Signal

from save_parser import parse_save
from mewgenics.utils.cat_persistence import (
    _load_blacklist, _load_must_breed, _load_pinned, _load_tags,
)
from mewgenics.utils.calibration import _load_gender_overrides, _apply_calibration


class SaveLoadWorker(QThread):
    """Parses a save file off the main thread so the UI stays responsive."""
    status = Signal(str)  # status text updates
    finished_load = Signal(object)  # emits dict with parsed results

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        self.status.emit("Parsing save file…")
        save = parse_save(self._path)
        cats, errors, unlocked_house_rooms = save
        self.status.emit("Loading blacklist & overrides…")
        _load_blacklist(self._path, cats)
        _load_must_breed(self._path, cats)
        _load_pinned(self._path, cats)
        _load_tags(self._path, cats)
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
