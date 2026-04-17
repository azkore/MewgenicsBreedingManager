"""Blacklist, must-breed, pinned, and tags load/save."""
import json
import logging
import os
import tempfile

from save_parser import Cat

from mewgenics.utils.paths import _blacklist_path, _must_breed_path, _pinned_path, _tags_path, _not_adventured_path
from mewgenics.utils.tags import _TAG_DEFS, _cat_tags

logger = logging.getLogger("mewgenics.cat_persistence")


def _atomic_write_text(path: str, content: str):
    parent = os.path.dirname(path) or "."
    tmp_fd = None
    tmp_path = None
    try:
        os.makedirs(parent, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".cat_state.", suffix=".tmp", dir=parent
        )
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            tmp_fd = None
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
        tmp_path = None
    except OSError:
        logger.warning("failed to write sidecar at %s", path, exc_info=True)
    finally:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _load_uid_set(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        logger.warning("failed to read sidecar at %s", path, exc_info=True)
        return set()


def _save_uid_flag_list(path: str, cats: list[Cat], attr_name: str):
    selected_uids = [c.unique_id for c in cats if getattr(c, attr_name, False)]
    _atomic_write_text(path, "\n".join(selected_uids))


def _load_uid_flag_list(path: str, cats: list[Cat], attr_name: str):
    selected_uids = _load_uid_set(path)
    if not selected_uids:
        return
    for cat in cats:
        setattr(cat, attr_name, cat.unique_id in selected_uids)


def _load_json_dict(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        logger.warning("failed to read JSON sidecar at %s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _save_blacklist(save_path: str, cats: list[Cat]):
    """Save blacklisted cat unique IDs to file."""
    _save_uid_flag_list(_blacklist_path(save_path), cats, "is_blacklisted")


def _load_blacklist(save_path: str, cats: list[Cat]):
    """Load blacklist and mark cats accordingly."""
    _load_uid_flag_list(_blacklist_path(save_path), cats, "is_blacklisted")


def _save_must_breed(save_path: str, cats: list[Cat]):
    """Save must-breed cat unique IDs to file."""
    _save_uid_flag_list(_must_breed_path(save_path), cats, "must_breed")


def _load_must_breed(save_path: str, cats: list[Cat]):
    """Load must-breed list and mark cats accordingly."""
    _load_uid_flag_list(_must_breed_path(save_path), cats, "must_breed")


def _save_pinned(save_path: str, cats: list[Cat]):
    """Save pinned cat unique IDs to file."""
    _save_uid_flag_list(_pinned_path(save_path), cats, "is_pinned")


def _load_pinned(save_path: str, cats: list[Cat]):
    """Load pinned list and mark cats accordingly."""
    _load_uid_flag_list(_pinned_path(save_path), cats, "is_pinned")


def _save_tags(save_path: str, cats: list[Cat]):
    """Save cat tag assignments to JSON sidecar."""
    tags_file = _tags_path(save_path)
    valid_ids = {td["id"] for td in _TAG_DEFS}
    data = {}
    for c in cats:
        tags = [t for t in _cat_tags(c) if t in valid_ids]
        if tags:
            data[c.unique_id] = tags
    try:
        _atomic_write_text(tags_file, json.dumps(data, indent=2, sort_keys=True))
    except Exception:
        logger.warning("failed to persist tag sidecar at %s", tags_file, exc_info=True)


def _save_not_adventured(save_path: str, cats: list[Cat]):
    """Save not-adventured override UIDs to file."""
    _save_uid_flag_list(_not_adventured_path(save_path), cats, "not_adventured_override")


def _load_not_adventured(save_path: str, cats: list[Cat]):
    """Load not-adventured overrides and mark cats accordingly."""
    _load_uid_flag_list(_not_adventured_path(save_path), cats, "not_adventured_override")


def _load_tags(save_path: str, cats: list[Cat]):
    """Load tag assignments from JSON sidecar and apply to cats."""
    data = _load_json_dict(_tags_path(save_path))
    if not data:
        return
    valid_ids = {td["id"] for td in _TAG_DEFS}
    for cat in cats:
        raw = data.get(cat.unique_id, [])
        cat.tags = [t for t in raw if t in valid_ids]
