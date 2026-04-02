"""Tag definitions, icons, and pixmaps."""
import hashlib
from typing import Optional
from pathlib import Path

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QBrush, QPainter, QPixmap, QIcon, QPen, QPainterPath

from mewgenics.utils.config import _load_app_config, _save_app_config


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
_PIN_ICON_CACHE: dict[tuple[bool, int], QIcon] = {}


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
                scaled = pix.scaled(
                    int(rect.width()),
                    int(rect.height()),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                painter.save()
                clip = QPainterPath()
                radius = max(2.0, min(rect.width(), rect.height()) * 0.33)
                clip.addRoundedRect(rect, radius, radius)
                painter.setClipPath(clip)
                painter.drawPixmap(rect.toRect(), scaled, scaled.rect())
                painter.restore()
                border = QColor(str(td.get("color", "#555555") or "#555555"))
                painter.setPen(QPen(border.darker(130), 0.8))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
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
                scaled = pix.scaled(
                    int(rect.width()),
                    int(rect.height()),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                painter.save()
                clip = QPainterPath()
                clip.addRect(rect)
                painter.setClipPath(clip)
                painter.drawPixmap(rect.toRect(), scaled, scaled.rect())
                painter.restore()
                border = QColor(str(td.get("color", "#32425f") or "#32425f"))
                painter.setPen(QPen(border.darker(130), 0.8))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
                return

    color = QColor(_game_tag_color(td.get("id", td.get("name", ""))))
    painter.setBrush(QBrush(color))
    painter.setPen(QColor(color.darker(150)))
    painter.drawRect(rect)


def _make_game_tag_icon(tag_values: list[str], dot_size: int = 10, spacing: int = 3) -> QIcon:
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


def _make_game_tag_pixmap(tag_values: list[str], dot_size: int = 10, spacing: int = 3) -> Optional[QPixmap]:
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


def _make_tag_icon(tag_ids: list[str], dot_size: int = 10, spacing: int = 3) -> QIcon:
    """Create a QIcon for the given tag IDs, ordered by definition."""
    if not tag_ids:
        return QIcon()
    valid_defs = _tag_defs_for_ids(tag_ids)
    if not valid_defs:
        return QIcon()
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing))
    if cache_key in _TAG_ICON_CACHE:
        return _TAG_ICON_CACHE[cache_key]
    width = len(valid_defs) * (dot_size + spacing) - spacing + 2
    height = dot_size + 2
    pix = QPixmap(width, height)
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
    cache_key = tuple(
        (td.get("id"), td.get("color"), td.get("image_path", ""))
        for td in valid_defs
    ) + (int(dot_size), int(spacing))
    if cache_key in _TAG_PIX_CACHE:
        return _TAG_PIX_CACHE[cache_key]
    width = len(valid_defs) * (dot_size + spacing) - spacing + 4
    height = dot_size + 4
    pix = QPixmap(width, height)
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
    cache_key = (bool(active), int(size))
    cached = _PIN_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    pix = QPixmap(size, size)
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
