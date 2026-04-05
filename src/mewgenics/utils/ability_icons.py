"""Ability/passive icon extraction from the game's ability_icons.swf."""
from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap


_ABILITY_SWF_NAME = "swfs/ability_icons.swf"
_ABILITY_SPRITE_ID = 1346
_PASSIVE_SPRITE_ID = 515


@dataclass(slots=True)
class _Definition:
    code: int
    payload: bytes


class _BitReader:
    def __init__(self, data: bytes, byte_offset: int):
        self._data = data
        self._bitpos = byte_offset * 8

    def read(self, bits: int) -> int:
        if bits <= 0:
            return 0
        value = 0
        for _ in range(bits):
            byte = self._data[self._bitpos // 8]
            bit = 7 - (self._bitpos % 8)
            value = (value << 1) | ((byte >> bit) & 1)
            self._bitpos += 1
        return value

    def read_signed(self, bits: int) -> int:
        if bits <= 0:
            return 0
        value = self.read(bits)
        sign_bit = 1 << (bits - 1)
        if value & sign_bit:
            value -= 1 << bits
        return value

    def align(self):
        rem = self._bitpos % 8
        if rem:
            self._bitpos += 8 - rem

    def tell(self) -> int:
        return self._bitpos // 8


_CURRENT_GPAK_PATH: str | None = None
_DEFINITIONS: dict[int, _Definition] = {}
_ABILITY_LABEL_TO_SYMBOL: dict[str, int] = {}
_PASSIVE_LABEL_TO_SYMBOL: dict[str, int] = {}
_ABILITY_LABEL_TO_SYMBOL_NORM: dict[str, int] = {}
_PASSIVE_LABEL_TO_SYMBOL_NORM: dict[str, int] = {}
_RENDER_CACHE: dict[tuple[str, str, int], QPixmap] = {}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _gpak_entry_bytes(gpak_path: str | None, target_name: str) -> bytes | None:
    if not gpak_path:
        return None
    try:
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
    except Exception:
        return None
    return None


def _swf_rect_size(data: bytes, offset: int) -> int:
    if offset >= len(data):
        return 0
    nbits = data[offset] >> 3
    bit_length = 5 + (4 * nbits)
    return (bit_length + 7) // 8


def _read_rect(br: _BitReader) -> QRectF:
    nbits = br.read(5)
    x_min = br.read_signed(nbits)
    x_max = br.read_signed(nbits)
    y_min = br.read_signed(nbits)
    y_max = br.read_signed(nbits)
    br.align()
    return QRectF(
        x_min / 20.0,
        y_min / 20.0,
        (x_max - x_min) / 20.0,
        (y_max - y_min) / 20.0,
    )


def _skip_matrix(br: _BitReader):
    if br.read(1):
        bits = br.read(5)
        br.read_signed(bits)
        br.read_signed(bits)
    if br.read(1):
        bits = br.read(5)
        br.read_signed(bits)
        br.read_signed(bits)
    bits = br.read(5)
    br.read_signed(bits)
    br.read_signed(bits)
    br.align()


def _read_color(br: _BitReader, rgba: bool) -> QColor:
    red = br.read(8)
    green = br.read(8)
    blue = br.read(8)
    alpha = br.read(8) if rgba else 255
    return QColor(red, green, blue, alpha)


def _fallback_fill_color(token: int) -> QColor:
    digest = hashlib.sha1(str(token).encode("utf-8")).digest()
    return QColor(
        72 + digest[0] // 2,
        72 + digest[1] // 2,
        96 + digest[2] // 3,
        255,
    )


def _skip_gradient(br: _BitReader, rgba: bool, focal: bool) -> QColor:
    br.read(2)  # spread mode
    br.read(2)  # interpolation mode
    count = br.read(4)
    first = None
    for _ in range(count):
        br.read(8)  # ratio
        color = _read_color(br, rgba)
        if first is None:
            first = color
    if focal:
        br.read_signed(16)
    return first or QColor("#808080")


def _read_fill_style(br: _BitReader, style_type: int, rgba: bool) -> QColor:
    if style_type == 0x00:
        br.align()
        return _read_color(br, rgba)
    if style_type in {0x10, 0x12, 0x13}:
        br.align()
        _skip_matrix(br)
        return _skip_gradient(br, rgba, style_type == 0x13)
    if style_type in {0x40, 0x41, 0x42}:
        br.align()
        bitmap_id = br.read(16)
        _skip_matrix(br)
        return _fallback_fill_color(bitmap_id + style_type)
    return _fallback_fill_color(style_type)


def _read_fill_styles(br: _BitReader, code: int) -> list[QColor]:
    count = br.read(8)
    if count == 0xFF:
        count = br.read(16)
    rgba = code in {32, 83}
    colors: list[QColor] = []
    for _ in range(count):
        style_type = br.read(8)
        colors.append(_read_fill_style(br, style_type, rgba))
    return colors


def _read_line_styles(br: _BitReader, code: int) -> None:
    count = br.read(8)
    if count == 0xFF:
        count = br.read(16)
    rgba = code in {32, 83}
    for _ in range(count):
        if code == 83:
            br.read(16)  # width
            br.read(2)  # start cap
            join_style = br.read(2)
            has_fill = br.read(1)
            br.read(1)  # no horizontal scale
            br.read(1)  # no vertical scale
            br.read(1)  # pixel hinting
            br.read(5)  # reserved
            br.read(1)  # no close
            br.read(2)  # end cap
            if join_style == 2:
                br.read(16)  # miter limit factor
            if has_fill:
                _read_fill_style(br, br.read(8), True)
            else:
                _read_color(br, rgba)
        else:
            br.read(16)
            br.align()
            _read_color(br, rgba)


def _parse_shape(code: int, payload: bytes) -> tuple[QRectF, list[tuple[QColor, QPainterPath]]]:
    if code == 83:
        br = _BitReader(payload, 2)
        bounds = _read_rect(br)
        _ = _read_rect(br)  # edge bounds
        br.read(5)  # reserved
        br.read(1)  # usesFillWindingRule
        br.read(1)  # usesNonScalingStrokes
        br.read(1)  # usesScalingStrokes
    else:
        br = _BitReader(payload, 2)
        bounds = _read_rect(br)

    fill_styles = _read_fill_styles(br, code)
    _read_line_styles(br, code)
    fill_bits = br.read(4)
    line_bits = br.read(4)

    contours: list[tuple[QColor, QPainterPath]] = []
    current_path = QPainterPath()
    current_fill0 = 0
    current_fill1 = 0
    current_line = 0
    current_pos = QPointF(0.0, 0.0)
    current_fill_color = QColor()

    def _sync_fill_color():
        nonlocal current_fill_color
        current_fill_index = current_fill1 or current_fill0
        if 1 <= current_fill_index <= len(fill_styles):
            current_fill_color = QColor(fill_styles[current_fill_index - 1])
        else:
            current_fill_color = QColor()

    def _commit_path():
        nonlocal current_path, current_fill_color
        if current_fill_color.isValid() and current_path.elementCount() > 1:
            path = QPainterPath(current_path)
            path.closeSubpath()
            contours.append((QColor(current_fill_color), path))
        current_path = QPainterPath()
        current_fill_color = QColor()

    while True:
        type_flag = br.read(1)
        if type_flag == 0:
            flags = br.read(5)
            if flags == 0:
                break
            if flags & 0b00001:
                _commit_path()
                move_bits = br.read(5)
                current_pos = QPointF(br.read_signed(move_bits) / 20.0, br.read_signed(move_bits) / 20.0)
                current_path.moveTo(current_pos)
                _sync_fill_color()
            if flags & 0b00010:
                current_fill0 = br.read(fill_bits)
                _sync_fill_color()
            if flags & 0b00100:
                current_fill1 = br.read(fill_bits)
                _sync_fill_color()
            if flags & 0b01000:
                current_line = br.read(line_bits)
            if flags & 0b10000:
                _commit_path()
                br.align()
                fill_styles.extend(_read_fill_styles(br, code))
                _read_line_styles(br, code)
                fill_bits = br.read(4)
                line_bits = br.read(4)
        else:
            straight_flag = br.read(1)
            if straight_flag:
                edge_bits = br.read(4) + 2
                general_flag = br.read(1)
                if general_flag:
                    dx = br.read_signed(edge_bits)
                    dy = br.read_signed(edge_bits)
                else:
                    vertical = br.read(1)
                    if vertical:
                        dx = 0
                        dy = br.read_signed(edge_bits)
                    else:
                        dx = br.read_signed(edge_bits)
                        dy = 0
                if current_path.isEmpty():
                    current_path.moveTo(current_pos)
                    _sync_fill_color()
                current_pos = QPointF(current_pos.x() + dx / 20.0, current_pos.y() + dy / 20.0)
                current_path.lineTo(current_pos)
            else:
                curve_bits = br.read(4) + 2
                control_dx = br.read_signed(curve_bits)
                control_dy = br.read_signed(curve_bits)
                anchor_dx = br.read_signed(curve_bits)
                anchor_dy = br.read_signed(curve_bits)
                if current_path.isEmpty():
                    current_path.moveTo(current_pos)
                    _sync_fill_color()
                control = QPointF(
                    current_pos.x() + control_dx / 20.0,
                    current_pos.y() + control_dy / 20.0,
                )
                current_pos = QPointF(
                    current_pos.x() + control_dx / 20.0 + anchor_dx / 20.0,
                    current_pos.y() + control_dy / 20.0 + anchor_dy / 20.0,
                )
                current_path.quadTo(control, current_pos)

    _commit_path()
    return bounds, contours


def _iterate_tags(data: bytes):
    pos = 8 + _swf_rect_size(data, 8) + 4
    while pos + 2 <= len(data):
        rec = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = rec >> 6
        length = rec & 0x3F
        if length == 0x3F:
            if pos + 4 > len(data):
                break
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if pos + length > len(data):
            break
        payload = data[pos:pos + length]
        pos += length
        yield code, payload
        if code == 0:
            break


def _parse_swf_definition_map(data: bytes) -> dict[int, _Definition]:
    defs: dict[int, _Definition] = {}
    for code, payload in _iterate_tags(data):
        if len(payload) < 2:
            continue
        if code in {2, 22, 32, 37, 39, 83}:
            defs[struct.unpack_from("<H", payload, 0)[0]] = _Definition(code=code, payload=payload)
    return defs


def _place_object_char_id(payload: bytes) -> int | None:
    if len(payload) < 3:
        return None
    flags = payload[0]
    offset = 3
    if flags & 0x02:
        if offset + 2 > len(payload):
            return None
        return struct.unpack_from("<H", payload, offset)[0]
    return None


def _parse_sprite_label_map(data: bytes, sprite_id: int) -> dict[str, int]:
    sprite_payload = _DEFINITIONS.get(sprite_id)
    if sprite_payload is None or sprite_payload.code != 39:
        return {}

    payload = sprite_payload.payload
    inner = payload[4:]
    current_label: str | None = None
    placed_ids: list[int] = []
    label_map: dict[str, int] = {}

    ipos = 0
    while ipos + 2 <= len(inner):
        rec = struct.unpack_from("<H", inner, ipos)[0]
        ipos += 2
        code = rec >> 6
        length = rec & 0x3F
        if length == 0x3F:
            if ipos + 4 > len(inner):
                break
            length = struct.unpack_from("<I", inner, ipos)[0]
            ipos += 4
        if ipos + length > len(inner):
            break
        tag_payload = inner[ipos:ipos + length]
        ipos += length

        if code == 43:
            end = tag_payload.find(b"\x00")
            if end >= 0:
                current_label = tag_payload[:end].decode("utf-8", errors="replace").strip()
            else:
                current_label = tag_payload.decode("utf-8", errors="replace").strip()
        elif code in {26, 70}:
            char_id = _place_object_char_id(tag_payload)
            if char_id is not None:
                placed_ids.append(char_id)
        elif code == 1:
            if current_label:
                for char_id in reversed(placed_ids):
                    definition = _DEFINITIONS.get(char_id)
                    if definition is None:
                        continue
                    if definition.code in {2, 22, 32, 37, 39, 83}:
                        label_map[current_label] = char_id
                        break
            current_label = None
            placed_ids = []
        elif code == 0:
            break

    return label_map


def _reload_ability_icon_cache(gpak_path: str | None):
    global _CURRENT_GPAK_PATH, _DEFINITIONS, _ABILITY_LABEL_TO_SYMBOL, _PASSIVE_LABEL_TO_SYMBOL
    global _ABILITY_LABEL_TO_SYMBOL_NORM, _PASSIVE_LABEL_TO_SYMBOL_NORM
    _CURRENT_GPAK_PATH = gpak_path
    _DEFINITIONS = {}
    _ABILITY_LABEL_TO_SYMBOL = {}
    _PASSIVE_LABEL_TO_SYMBOL = {}
    _ABILITY_LABEL_TO_SYMBOL_NORM = {}
    _PASSIVE_LABEL_TO_SYMBOL_NORM = {}
    _RENDER_CACHE.clear()

    raw = _gpak_entry_bytes(gpak_path, _ABILITY_SWF_NAME)
    if not raw:
        return
    if raw[:3] == b"CWS":
        try:
            data = raw[:8] + zlib.decompress(raw[8:])
        except Exception:
            return
    else:
        data = raw

    _DEFINITIONS = _parse_swf_definition_map(data)
    _ABILITY_LABEL_TO_SYMBOL = _parse_sprite_label_map(data, _ABILITY_SPRITE_ID)
    _PASSIVE_LABEL_TO_SYMBOL = _parse_sprite_label_map(data, _PASSIVE_SPRITE_ID)
    _ABILITY_LABEL_TO_SYMBOL_NORM = {_normalize_key(key): value for key, value in _ABILITY_LABEL_TO_SYMBOL.items()}
    _PASSIVE_LABEL_TO_SYMBOL_NORM = {_normalize_key(key): value for key, value in _PASSIVE_LABEL_TO_SYMBOL.items()}


def _ensure_loaded():
    from mewgenics.utils.game_data import get_gpak_path

    gpak_path = get_gpak_path()
    if gpak_path != _CURRENT_GPAK_PATH:
        _reload_ability_icon_cache(gpak_path)


def _icon_symbol_id(name: str, *, passive: bool = False) -> int | None:
    _ensure_loaded()
    normalized = _normalize_key(name)
    if not normalized:
        return None

    mapping = _PASSIVE_LABEL_TO_SYMBOL_NORM if passive else _ABILITY_LABEL_TO_SYMBOL_NORM
    if normalized in mapping:
        return mapping[normalized]

    raw = str(name or "").strip()
    if "_" in raw:
        base = raw.split("_", 1)[0]
        base_key = _normalize_key(base)
        if base_key in mapping:
            return mapping[base_key]

    # Some labels in the SWF use slightly different punctuation.
    raw_mapping = _PASSIVE_LABEL_TO_SYMBOL if passive else _ABILITY_LABEL_TO_SYMBOL
    for label_key, symbol_id in raw_mapping.items():
        label_norm = _normalize_key(label_key)
        if label_norm == normalized:
            return symbol_id
        if normalized.startswith(label_norm):
            return symbol_id

    return None


def _shape_pixmap(symbol_id: int, size: int) -> QPixmap | None:
    definition = _DEFINITIONS.get(symbol_id)
    if definition is None:
        return None
    cache_key = (definition.code, str(symbol_id), int(size))
    cached = _RENDER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if definition.code not in {2, 22, 32, 83}:
        return None

    try:
        bounds, contours = _parse_shape(definition.code, definition.payload)
    except Exception:
        return None
    if not contours:
        return None

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Use the actual shape bounds if they are usable; otherwise fall back to
    # the painted content bounds.
    target_bounds = bounds if bounds.isValid() and bounds.width() > 0 and bounds.height() > 0 else None
    if target_bounds is None:
        combined = QRectF()
        for _, path in contours:
            rect = path.boundingRect()
            combined = rect if combined.isNull() else combined.united(rect)
        target_bounds = combined

    if not target_bounds.isValid() or target_bounds.width() <= 0 or target_bounds.height() <= 0:
        painter.end()
        return None

    pad = max(1.0, size * 0.08)
    scale = min(
        (size - 2 * pad) / target_bounds.width(),
        (size - 2 * pad) / target_bounds.height(),
    )
    dx = (size - target_bounds.width() * scale) * 0.5
    dy = (size - target_bounds.height() * scale) * 0.5

    painter.translate(dx - target_bounds.left() * scale, dy - target_bounds.top() * scale)
    painter.scale(scale, scale)

    for color, path in contours:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)

    painter.end()
    _RENDER_CACHE[cache_key] = pix
    return pix


def get_ability_icon_pixmap(name: str, size: int = 16) -> QPixmap | None:
    symbol_id = _icon_symbol_id(name, passive=False)
    if symbol_id is None:
        return None
    return _shape_pixmap(symbol_id, size)


def get_passive_icon_pixmap(name: str, size: int = 16) -> QPixmap | None:
    symbol_id = _icon_symbol_id(name, passive=True)
    if symbol_id is None:
        return None
    return _shape_pixmap(symbol_id, size)
