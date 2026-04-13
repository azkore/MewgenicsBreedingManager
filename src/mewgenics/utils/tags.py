"""Tag definitions, icons, and pixmaps."""
import hashlib
import re
import shutil
from typing import Optional
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QBrush, QPainter, QPixmap, QIcon, QPen, QPainterPath

from mewgenics.utils.config import _load_app_config, _save_app_config
from mewgenics.utils.paths import APPDATA_CONFIG_DIR, _app_dir, _bundle_dir


TAG_PRESET_COLORS = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71",
    "#3498db", "#9b59b6", "#e91e8a", "#95a5a6",
]

_TAG_DEFS: list[dict] = []  # [{id, name, color}, ...]
_GAME_TAG_DEFS: list[dict] = []  # [{id, name, color, image_path, tooltip, source}, ...]
_TAG_ICON_CACHE: dict[tuple, QIcon] = {}
_TAG_PIX_CACHE: dict[tuple, QPixmap] = {}
_GAME_TAG_ICON_CACHE: dict[tuple, QIcon] = {}
_GAME_TAG_PIX_CACHE: dict[tuple, QPixmap] = {}
_CAT_TAG_PIX_CACHE: dict[tuple, QPixmap] = {}
_PIN_ICON_CACHE: dict[tuple[bool, int], QIcon] = {}
_GAME_ICON_IMAGE_CACHE: dict[str, QPixmap] = {}
_GAME_ICON_ATLAS_CACHE: dict[str, QPixmap] = {}
_GAME_ICON_PIX_CACHE: dict[tuple[str, int], QPixmap] = {}

_GAME_ICON_ATLAS_GRID = (5, 5)
# Best-effort file names for the named icon assets found in the repo.
_GAME_ICON_FILES = {
    "square": ("square.png",),
    "star": ("star.png",),
    "star2": ("star.png",),
    "circle": ("circle.png",),
    "triangle": ("triangle.png",),
    "sword": ("sword.png",),
    "shield": ("shield.png",),
    "poop": ("poop.png",),
    "health": ("medicine.png", "medical.png", "sleeping cat.png"),
    "medical": ("medical.png", "medicine.png"),
    "medicine": ("medicine.png", "medical.png"),
    "mutation": ("mutation.png",),
    "evolution": ("mutation.png",),
    "house": ("house.png",),
    "comfort": ("house.png",),
    "yarn": ("yarn.png",),
    "stimulation": ("yarn.png",),
    "str": ("STR.png",),
    "strength": ("STR.png",),
    "dex": ("DEX.png",),
    "dexterity": ("DEX.png",),
    "con": ("constitution.png",),
    "constitution": ("constitution.png",),
    "int": ("INT.png",),
    "intelligence": ("INT.png",),
    "lck": ("LCK.png",),
    "luck": ("LCK.png",),
    "spd": ("SPD.png",),
    "speed": ("SPD.png",),
    "cha": ("CHA.png",),
    "charisma": ("CHA.png",),
}
# Best-effort atlas coordinates for the common in-game name tags.
_GAME_ICON_COORDS = {
    "square": (0, 0),
    "star": (0, 1),
    "star2": (0, 1),
    "circle": (0, 2),
    "triangle": (0, 3),
    "sword": (0, 4),
    "shield": (1, 0),
    "poop": (1, 1),
    "health": (1, 2),
    "appeal": (1, 3),
    "cha": (1, 4),
    "charisma": (1, 4),
    "str": (2, 0),
    "strength": (2, 0),
    "dex": (2, 1),
    "dexterity": (2, 1),
    "con": (2, 2),
    "constitution": (2, 2),
    "int": (2, 3),
    "intelligence": (2, 3),
    "spd": (2, 4),
    "speed": (2, 4),
    "lck": (3, 0),
    "luck": (3, 0),
    "stimulation": (3, 1),
    "comfort": (3, 2),
    "evolution": (3, 3),
    "house": (3, 4),
}


def _normalize_color_value(color_value: object, default: str = "#555555") -> str:
    text = str(color_value or "").strip()
    if not text:
        return default
    color = QColor(text)
    if not color.isValid() and not text.startswith("#"):
        candidate = text
        if candidate.lower().startswith("0x"):
            candidate = candidate[2:]
        if len(candidate) in {3, 6}:
            try:
                int(candidate, 16)
            except ValueError:
                pass
            else:
                if len(candidate) == 3:
                    candidate = "".join(ch * 2 for ch in candidate)
                color = QColor(f"#{candidate}")
    return color.name() if color.isValid() else default


def _normalize_tag_definition(tag_def: dict | None) -> dict | None:
    if not isinstance(tag_def, dict):
        return None
    tag_id = str(tag_def.get("id", "")).strip()
    if not tag_id:
        return None
    normalized = dict(tag_def)
    normalized["id"] = tag_id
    normalized["name"] = str(normalized.get("name", "") or "").strip()
    normalized["color"] = _normalize_color_value(normalized.get("color", ""), "#555555")
    image_path = normalized.get("image_path", "")
    normalized["image_path"] = str(image_path).strip() if image_path else ""
    return normalized


def _normalize_game_tag_definition(tag_def: dict | None) -> dict | None:
    if not isinstance(tag_def, dict):
        return None
    tag_id = str(tag_def.get("id", "")).strip()
    tag_name = str(tag_def.get("name", "") or "").strip()
    image_path = str(tag_def.get("image_path", "") or "").strip()
    if not tag_id and not tag_name and not image_path:
        return None
    normalized = dict(tag_def)
    normalized["id"] = tag_id or tag_name
    normalized["name"] = tag_name or normalized["id"]
    normalized["color"] = _normalize_color_value(normalized.get("color", ""), "#32425f")
    normalized["image_path"] = image_path
    normalized["tooltip"] = str(normalized.get("tooltip", "") or "").strip()
    normalized["source"] = str(normalized.get("source", "") or "").strip()
    return normalized


def _tag_definition(tag_id: str) -> dict | None:
    for td in _TAG_DEFS:
        if td.get("id") == tag_id:
            return td
    return None


def _game_tag_definition(tag_value: str) -> dict | None:
    needle = str(tag_value or "").strip().lower()
    if not needle:
        return None
    for td in _GAME_TAG_DEFS:
        tag_id = str(td.get("id", "") or "").strip().lower()
        tag_name = str(td.get("name", "") or "").strip().lower()
        if needle == tag_id or needle == tag_name:
            return td
    return None


def _tag_image_path(tag_id: str) -> str:
    td = _tag_definition(tag_id)
    if td is None:
        return ""
    return str(td.get("image_path", "") or "").strip()


def _game_tag_image_path(tag_value: str) -> str:
    td = _game_tag_definition(tag_value)
    if td is None:
        return ""
    return str(td.get("image_path", "") or "").strip()


def _load_tag_definitions():
    """Load tag definitions from app config into module global."""
    global _TAG_DEFS
    cfg = _load_app_config()
    defs = cfg.get("tag_definitions", [])
    if not isinstance(defs, list):
        defs = []
    normalized = []
    for td in defs:
        item = _normalize_tag_definition(td)
        if item is not None:
            normalized.append(item)
    _TAG_DEFS = normalized
    _CAT_TAG_PIX_CACHE.clear()


def _load_game_tag_definitions(tag_defs: Optional[list[dict]] = None):
    """Load game-provided tag definitions from GPAK into module global."""
    global _GAME_TAG_DEFS
    normalized = []
    for td in tag_defs or []:
        item = _normalize_game_tag_definition(td)
        if item is not None:
            normalized.append(item)
    _GAME_TAG_DEFS = normalized
    _GAME_TAG_ICON_CACHE.clear()
    _GAME_TAG_PIX_CACHE.clear()
    _CAT_TAG_PIX_CACHE.clear()


def _save_tag_definitions():
    """Save current tag definitions to app config."""
    normalized = []
    for td in _TAG_DEFS:
        item = _normalize_tag_definition(td)
        if item is not None:
            normalized.append(item)
    _TAG_DEFS[:] = normalized
    cfg = _load_app_config()
    cfg["tag_definitions"] = normalized
    _save_app_config(cfg)
    _TAG_ICON_CACHE.clear()
    _TAG_PIX_CACHE.clear()
    _CAT_TAG_PIX_CACHE.clear()


def _game_tag_color(tag_value: str) -> str:
    """Look up hex color for a game tag value, defaulting to a stable hash color."""
    td = _game_tag_definition(tag_value)
    if td is not None:
        return _normalize_color_value(td.get("color", "#32425f"), "#32425f")
    text = str(tag_value or "").strip()
    if not text:
        return "#32425f"
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    r = 48 + digest[0] // 3
    g = 64 + digest[1] // 3
    b = 96 + digest[2] // 3
    return QColor(r, g, b).name()


def _game_tag_name(tag_value: str) -> str:
    td = _game_tag_definition(tag_value)
    if td is None:
        return str(tag_value or "").strip()
    return str(td.get("name", "") or "").strip() or str(tag_value or "").strip()


def _game_tag_tooltip(tag_value: str) -> str:
    td = _game_tag_definition(tag_value)
    if td is None:
        return str(tag_value or "").strip()
    tooltip = str(td.get("tooltip", "") or "").strip()
    source = str(td.get("source", "") or "").strip()
    name = _game_tag_name(tag_value)
    parts = [name]
    if tooltip:
        parts.append(tooltip)
    if source:
        parts.append(f"Source: {source}")
    return "\n".join(parts)


def _game_tag_token(tag_value: str) -> str:
    text = _game_tag_name(tag_value).strip()
    if not text:
        return "GT"
    parts = [part for part in text.replace("_", " ").split() if part]
    if len(parts) >= 2:
        token = "".join(part[0] for part in parts[:2])
    else:
        token = text[:2]
    return token.upper()


def _normalize_icon_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _game_icon_atlas_candidates() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    bundle_dir = Path(_bundle_dir())
    app_dir = Path(_app_dir())
    return [
        repo_root / "tools" / "icons" / "Icons without background.png",
        repo_root / "tools" / "icons" / "Icons.png",
        repo_root / "tools" / "icons" / "icons.png",
        bundle_dir / "icons" / "Icons without background.png",
        bundle_dir / "icons" / "Icons.png",
        bundle_dir / "icons" / "icons.png",
        app_dir / "icons" / "Icons without background.png",
        app_dir / "icons" / "Icons.png",
        app_dir / "icons" / "icons.png",
    ]


def _load_game_icon_atlas() -> Optional[QPixmap]:
    for candidate in _game_icon_atlas_candidates():
        if not candidate.exists():
            continue
        key = str(candidate.resolve())
        cached = _GAME_ICON_ATLAS_CACHE.get(key)
        if cached is not None:
            return cached
        pix = QPixmap(str(candidate))
        if pix.isNull():
            continue
        _GAME_ICON_ATLAS_CACHE[key] = pix
        return pix
    return None


def _game_icon_cell(tag_value: str) -> tuple[int, int] | None:
    key = _normalize_icon_key(tag_value)
    if not key:
        return None
    return _GAME_ICON_COORDS.get(key)


def _game_icon_file_candidates(tag_value: str) -> list[Path]:
    key = _normalize_icon_key(tag_value)
    names = _GAME_ICON_FILES.get(key, ())
    if not names:
        return []
    repo_root = Path(__file__).resolve().parents[3]
    bundle_dir = Path(_bundle_dir())
    app_dir = Path(_app_dir())
    roots = [
        repo_root / "images" / "White",
        bundle_dir / "images" / "White",
        app_dir / "images" / "White",
        repo_root / "images" / "Black",
        bundle_dir / "images" / "Black",
        app_dir / "images" / "Black",
        repo_root / "tools" / "icons",
        repo_root / "images",
        bundle_dir / "icons",
        bundle_dir / "images",
        app_dir / "icons",
        app_dir / "images",
    ]
    candidates: list[Path] = []
    for root in roots:
        for name in names:
            candidates.append(root / name)
    return candidates


def _trim_transparent_pixmap(pix: QPixmap) -> QPixmap:
    if pix.isNull():
        return pix
    img = pix.toImage()
    width = img.width()
    height = img.height()
    left = width
    top = height
    right = -1
    bottom = -1
    for y in range(height):
        for x in range(width):
            if img.pixelColor(x, y).alpha() > 8:
                if x < left:
                    left = x
                if y < top:
                    top = y
                if x > right:
                    right = x
                if y > bottom:
                    bottom = y
    if right < left or bottom < top:
        return pix
    return QPixmap.fromImage(img.copy(left, top, right - left + 1, bottom - top + 1))


def _load_game_icon_image(tag_value: str, size: int) -> Optional[QPixmap]:
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    key = (_normalize_icon_key(tag_value), int(size), dpr)
    cached = _GAME_ICON_PIX_CACHE.get(key)
    if cached is not None:
        return cached
    for candidate in _game_icon_file_candidates(tag_value):
        if not candidate.exists():
            continue
        cache_key = str(candidate.resolve())
        pix = _GAME_ICON_IMAGE_CACHE.get(cache_key)
        if pix is None:
            pix = QPixmap(str(candidate))
            if pix.isNull():
                continue
            pix = _trim_transparent_pixmap(pix)
            _GAME_ICON_IMAGE_CACHE[cache_key] = pix
        phys = max(1, int(size * dpr))
        scaled = pix
        if pix.width() != phys or pix.height() != phys:
            scaled = pix.scaled(phys, phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        _GAME_ICON_PIX_CACHE[key] = scaled
        return scaled
    return None


def _game_icon_pixmap(tag_value: str, size: int) -> Optional[QPixmap]:
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    key = (_normalize_icon_key(tag_value), int(size), dpr)
    cached = _GAME_ICON_PIX_CACHE.get(key)
    if cached is not None:
        return cached
    sprite = _load_game_icon_image(tag_value, size)
    if sprite is not None:
        return sprite
    atlas = _load_game_icon_atlas()
    cell = _game_icon_cell(tag_value)
    if atlas is None or cell is None:
        return None
    cols, rows = _GAME_ICON_ATLAS_GRID
    row, col = cell
    if row < 0 or col < 0 or row >= rows or col >= cols:
        return None
    cell_w = atlas.width() // cols
    cell_h = atlas.height() // rows
    if cell_w <= 0 or cell_h <= 0:
        return None
    crop = atlas.copy(col * cell_w, row * cell_h, cell_w, cell_h)
    if crop.isNull():
        return None
    crop = _trim_transparent_pixmap(crop)
    phys = max(1, int(size * dpr))
    if crop.width() != phys or crop.height() != phys:
        crop = crop.scaled(phys, phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    crop.setDevicePixelRatio(dpr)
    _GAME_ICON_PIX_CACHE[key] = crop
    return crop


def _tag_color(tag_id: str) -> str:
    """Look up hex color for a tag ID, default gray."""
    td = _tag_definition(tag_id)
    if td is None:
        return "#555555"
    return _normalize_color_value(td.get("color", "#555555"), "#555555")


def _game_tag_defs() -> list[dict]:
    return list(_GAME_TAG_DEFS)


def _tag_name(tag_id: str) -> str:
    """Look up display name for a tag ID."""
    td = _tag_definition(tag_id)
    if td is None:
        return ""
    return str(td.get("name", "") or "")


def _next_tag_id() -> str:
    """Generate the next sequential tag ID."""
    existing = {td["id"] for td in _TAG_DEFS}
    i = 1
    while f"tag_{i}" in existing:
        i += 1
    return f"tag_{i}"


def _cat_tags(cat) -> list[str]:
    """Safely get tags list from a Cat, handling missing attribute."""
    return getattr(cat, 'tags', None) or []


def _tag_asset_dir() -> Path:
    path = Path(APPDATA_CONFIG_DIR) / "tag_assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_filename_part(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(text or "").strip())
    return cleaned.strip("_") or "tag"


def _import_tag_image(source_path: str, tag_id: str | None = None) -> str:
    source = Path(str(source_path or "")).expanduser()
    if not source.exists():
        return ""
    try:
        resolved = source.resolve()
    except Exception:
        resolved = source
    target_dir = _tag_asset_dir()
    try:
        if target_dir == resolved or target_dir in resolved.parents:
            return str(resolved)
    except Exception:
        pass

    try:
        payload = resolved.read_bytes()
    except Exception:
        payload = None
    digest = hashlib.sha1(payload if payload is not None else str(resolved).encode("utf-8")).hexdigest()[:16]
    suffix = resolved.suffix.lower() if resolved.suffix else ".png"
    prefix = _sanitize_filename_part(tag_id) if tag_id else "tag"
    filename = f"{prefix}_{digest}{suffix}" if prefix else f"{digest}{suffix}"
    dest = target_dir / filename

    try:
        if not dest.exists():
            shutil.copy2(str(resolved), str(dest))
        return str(dest)
    except Exception:
        return str(resolved)


def _tag_defs_in_order(tag_ids: list[str]) -> list[dict]:
    ordered: list[dict] = []
    seen: set[str] = set()
    for tag_id in tag_ids or []:
        tid = str(tag_id or "").strip()
        if not tid or tid in seen:
            continue
        td = _tag_definition(tid)
        if td is not None:
            ordered.append(td)
            seen.add(tid)
    return ordered


def _cat_tag_entries(cat) -> list[dict]:
    entries: list[dict] = []
    game_tag = str(getattr(cat, "name_tag", "") or "").strip()
    if game_tag:
        td = _game_tag_definition(game_tag)
        if td is None:
            entries.append({
                "kind": "game",
                "id": game_tag,
                "name": game_tag,
                "color": _game_tag_color(game_tag),
                "image_path": _game_tag_image_path(game_tag),
                "tooltip": "",
                "source": "",
            })
        else:
            entries.append({**td, "kind": "game"})
    for td in _tag_defs_in_order(_cat_tags(cat)):
        entries.append({**td, "kind": "custom"})
    return entries


def _cat_tag_labels(cat) -> list[str]:
    labels: list[str] = []
    for entry in _cat_tag_entries(cat):
        name = str(entry.get("name", "") or "").strip()
        if name:
            labels.append(name)
    return labels


def _cat_tag_summary(cat) -> str:
    labels = _cat_tag_labels(cat)
    return ", ".join(labels) if labels else "—"


def _cat_tag_tooltip(cat) -> str:
    entries = _cat_tag_entries(cat)
    if not entries:
        return "No tags assigned"
    lines: list[str] = []
    game_labels: list[str] = []
    custom_labels: list[str] = []
    for entry in entries:
        name = str(entry.get("name", "") or "").strip()
        if not name:
            continue
        if entry.get("kind") == "game":
            game_labels.append(name)
            tooltip = str(entry.get("tooltip", "") or "").strip()
            source = str(entry.get("source", "") or "").strip()
            if tooltip:
                lines.append(tooltip)
            if source:
                lines.append(f"Source: {source}")
        else:
            custom_labels.append(name)
    if game_labels:
        lines.insert(0, "Game tag: " + ", ".join(game_labels))
    if custom_labels:
        lines.append("Custom tags: " + ", ".join(custom_labels))
    return "\n".join(lines) if lines else "No tags assigned"


def _cat_tag_pixmap(cat, dot_size: int = 12, spacing: int = 4) -> Optional[QPixmap]:
    entries = _cat_tag_entries(cat)
    if not entries:
        return None
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    cache_key = tuple(
        (entry.get("kind"), entry.get("id"), entry.get("color"), entry.get("image_path", ""))
        for entry in entries
    ) + (int(dot_size), int(spacing), dpr)
    cached = _CAT_TAG_PIX_CACHE.get(cache_key)
    if cached is not None:
        return cached

    width = len(entries) * (dot_size + spacing) - spacing + 4
    height = dot_size + 4
    pix = QPixmap(int(width * dpr), int(height * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, entry in enumerate(entries):
        x = i * (dot_size + spacing) + 2
        rect = QRectF(x, 2, dot_size, dot_size)
        if entry.get("kind") == "game":
            _draw_game_tag_mark(painter, entry, rect, dot_size)
        else:
            _draw_tag_mark(painter, entry, rect, dot_size)
    painter.end()
    _CAT_TAG_PIX_CACHE[cache_key] = pix
    return pix


def _tag_defs_for_ids(tag_ids: list[str]) -> list[dict]:
    tag_set = set(tag_ids or [])
    return [td for td in _TAG_DEFS if td.get("id") in tag_set]


def _game_tag_defs_for_ids(tag_values: list[str]) -> list[dict]:
    want = [str(v or "").strip().lower() for v in (tag_values or []) if str(v or "").strip()]
    if not want:
        return []
    result = []
    for td in _GAME_TAG_DEFS:
        tag_id = str(td.get("id", "") or "").strip().lower()
        tag_name = str(td.get("name", "") or "").strip().lower()
        if tag_id in want or tag_name in want:
            result.append(td)
    return result


def _draw_tag_mark(painter: QPainter, td: dict, rect: QRectF, size: int):
    image_path = str(td.get("image_path", "") or "").strip()
    if image_path:
        path = Path(image_path).expanduser()
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                pix = _trim_transparent_pixmap(pix)
                dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
                target = max(1, int(min(int(rect.width()), int(rect.height())) * dpr))
                scaled = pix
                if pix.width() != target or pix.height() != target:
                    scaled = pix.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                painter.save()
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                clip = QPainterPath()
                radius = max(2.0, min(rect.width(), rect.height()) * 0.33)
                clip.addRoundedRect(rect, radius, radius)
                painter.setClipPath(clip)
                sw = scaled.width() / dpr
                sh = scaled.height() / dpr
                draw_x = rect.left() + max(0.0, (rect.width() - sw) * 0.5)
                draw_y = rect.top() + max(0.0, (rect.height() - sh) * 0.5)
                painter.drawPixmap(QPointF(draw_x, draw_y), scaled)
                painter.restore()
                return

    color = QColor(str(td.get("color", "#555555") or "#555555"))
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(rect)


def _draw_game_tag_mark(painter: QPainter, td: dict, rect: QRectF, size: int):
    image_path = str(td.get("image_path", "") or "").strip()
    if image_path:
        path = Path(image_path).expanduser()
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                pix = _trim_transparent_pixmap(pix)
                dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
                target = max(1, int(min(int(rect.width()), int(rect.height())) * dpr))
                scaled = pix
                if pix.width() != target or pix.height() != target:
                    scaled = pix.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                painter.save()
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                clip = QPainterPath()
                clip.addRect(rect)
                painter.setClipPath(clip)
                sw = scaled.width() / dpr
                sh = scaled.height() / dpr
                draw_x = rect.left() + max(0.0, (rect.width() - sw) * 0.5)
                draw_y = rect.top() + max(0.0, (rect.height() - sh) * 0.5)
                painter.drawPixmap(QPointF(draw_x, draw_y), scaled)
                painter.restore()
                return

    sprite = _game_icon_pixmap(str(td.get("id", td.get("name", "")) or ""), int(size))
    if sprite is not None and not sprite.isNull():
        draw_x = rect.left() + max(0.0, (rect.width() - sprite.width()) * 0.5)
        draw_y = rect.top() + max(0.0, (rect.height() - sprite.height()) * 0.5)
        painter.save()
        clip = QPainterPath()
        clip.addRect(rect)
        painter.setClipPath(clip)
        painter.drawPixmap(QPointF(draw_x, draw_y), sprite)
        painter.restore()
        return

    color = QColor(_game_tag_color(td.get("id", td.get("name", ""))))
    painter.setBrush(QBrush(color))
    painter.setPen(QColor(color.darker(150)))
    painter.drawRect(rect)


def _make_game_tag_icon(tag_values: list[str], dot_size: int = 12, spacing: int = 4) -> QIcon:
    """Create a QIcon for game tags, using square badges to distinguish them."""
    if not tag_values:
        return QIcon()
    valid_defs = _game_tag_defs_for_ids(tag_values)
    if not valid_defs:
        return QIcon()
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing))
    cached = _GAME_TAG_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    width = len(valid_defs) * (dot_size + spacing) - spacing + 2
    height = dot_size + 2
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, td in enumerate(valid_defs):
        x = i * (dot_size + spacing) + 1
        _draw_game_tag_mark(painter, td, QRectF(x, 1, dot_size, dot_size), dot_size)
    painter.end()
    icon = QIcon(pix)
    _GAME_TAG_ICON_CACHE[cache_key] = icon
    return icon


def _make_game_tag_pixmap(tag_values: list[str], dot_size: int = 12, spacing: int = 4) -> Optional[QPixmap]:
    """Create a QPixmap for game tags, using square badges to distinguish them."""
    if not tag_values:
        return None
    valid_defs = _game_tag_defs_for_ids(tag_values)
    if not valid_defs:
        return None
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing))
    cached = _GAME_TAG_PIX_CACHE.get(cache_key)
    if cached is not None:
        return cached
    width = len(valid_defs) * (dot_size + spacing) - spacing + 4
    height = dot_size + 4
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, td in enumerate(valid_defs):
        x = i * (dot_size + spacing) + 2
        _draw_game_tag_mark(painter, td, QRectF(x, 2, dot_size, dot_size), dot_size)
    painter.end()
    _GAME_TAG_PIX_CACHE[cache_key] = pix
    return pix


def _make_tag_icon(tag_ids: list[str], dot_size: int = 12, spacing: int = 4) -> QIcon:
    """Create a QIcon for the given tag IDs, ordered by definition."""
    if not tag_ids:
        return QIcon()
    valid_defs = _tag_defs_for_ids(tag_ids)
    if not valid_defs:
        return QIcon()
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing), dpr)
    if cache_key in _TAG_ICON_CACHE:
        return _TAG_ICON_CACHE[cache_key]
    width = len(valid_defs) * (dot_size + spacing) - spacing + 2
    height = dot_size + 2
    pix = QPixmap(int(width * dpr), int(height * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, td in enumerate(valid_defs):
        x = i * (dot_size + spacing) + 1
        _draw_tag_mark(painter, td, QRectF(x, 1, dot_size, dot_size), dot_size)
    painter.end()
    icon = QIcon(pix)
    _TAG_ICON_CACHE[cache_key] = icon
    return icon


def _make_tag_pixmap(tag_ids: list[str], dot_size: int = 10, spacing: int = 3) -> Optional[QPixmap]:
    """Create a QPixmap for the given tag IDs, ordered by definition."""
    if not tag_ids:
        return None
    valid_defs = _tag_defs_for_ids(tag_ids)
    if not valid_defs:
        return None
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing), dpr)
    if cache_key in _TAG_PIX_CACHE:
        return _TAG_PIX_CACHE[cache_key]
    width = len(valid_defs) * (dot_size + spacing) - spacing + 4
    height = dot_size + 4
    pix = QPixmap(int(width * dpr), int(height * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, td in enumerate(valid_defs):
        x = i * (dot_size + spacing) + 2
        _draw_tag_mark(painter, td, QRectF(x, 2, dot_size, dot_size), dot_size)
    painter.end()
    _TAG_PIX_CACHE[cache_key] = pix
    return pix


def _make_pin_icon(active: bool = True, size: int = 16) -> QIcon:
    """Create a compact pushpin icon for pin states."""
    dpr = getattr(QApplication.instance(), "devicePixelRatio", lambda: 1.0)()
    cache_key = (bool(active), int(size), dpr)
    cached = _PIN_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    phys = int(size * dpr)
    pix = QPixmap(phys, phys)
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    if active:
        head = QColor(224, 86, 86)
        stem = QColor(165, 52, 52)
        outline = QColor(86, 24, 24)
    else:
        head = QColor(118, 123, 154)
        stem = QColor(70, 74, 99)
        outline = QColor(30, 32, 44)

    # Leave a little breathing room so the glyph doesn't feel cramped in the button.
    painter.translate(size * 0.5, size * 0.5)
    painter.scale(0.86, 0.86)
    painter.rotate(-20)

    painter.setPen(QPen(outline, 0.8))
    painter.setBrush(QBrush(head))
    painter.drawEllipse(QPointF(0, -size * 0.18), size * 0.42, size * 0.42)

    path = QPainterPath()
    path.moveTo(-size * 0.05, -size * 0.02)
    path.lineTo(size * 0.10, size * 0.32)
    path.lineTo(-size * 0.08, size * 0.32)
    path.closeSubpath()
    painter.setBrush(QBrush(stem))
    painter.drawPath(path)
    painter.end()

    icon = QIcon(pix)
    _PIN_ICON_CACHE[cache_key] = icon
    return icon
