"""Colors, column indices, layout widths, and stylesheet constants."""
import re

from PySide6.QtGui import QColor

_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _blend_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )

# ── Stat / room / pair colors ────────────────────────────────────────────────

STAT_COLORS = {
    1: QColor(170, 40,  40),
    2: QColor(195, 85,  40),
    3: QColor(190, 145, 40),
    4: QColor(100, 100, 115),
    5: QColor(80,  160, 70),
    6: QColor(50,  195, 80),
    7: QColor(30,  215, 100),
}

_STAT_COLOR_START = STAT_COLORS[7]
_STAT_COLOR_END = QColor(10, 245, 180)
for value in range(8, 21):
    STAT_COLORS[value] = _blend_color(_STAT_COLOR_START, _STAT_COLOR_END, (value - 7) / 13.0)

ROOM_COLORS = {
    "Floor1_Large":   QColor(60, 100, 180),    # blue
    "Floor1_Small":   QColor(100, 140, 200),   # light blue
    "Floor2_Large":   QColor(180, 100, 60),    # orange
    "Floor2_Small":   QColor(200, 140, 100),   # light orange
    "Attic":          QColor(120, 100, 180),   # purple
}

PAIR_COLORS = [
    QColor(78, 126, 206),   # blue
    QColor(206, 126, 78),   # orange
    QColor(96, 182, 148),   # teal
    QColor(170, 108, 212),  # purple
    QColor(216, 152, 74),   # gold
    QColor(210, 98, 138),   # rose
    QColor(102, 170, 214),  # sky
    QColor(148, 184, 82),   # lime
]

STATUS_COLOR = {
    "In House":  QColor(50,  170, 110),
    "Adventure": QColor(70,  120, 200),
    "Gone":      QColor(80,   80,  90),
}


def _room_color(room_key: str | None) -> QColor:
    color = ROOM_COLORS.get(room_key, QColor(80, 80, 100))
    return QColor(color) if color.isValid() else QColor(80, 80, 100)


def _room_tint(room_key: str | None, strength: float = 0.2, lift: int = 16) -> QColor:
    color = _room_color(room_key)
    return QColor(
        min(255, int(color.red() * strength) + lift),
        min(255, int(color.green() * strength) + lift),
        min(255, int(color.blue() * strength) + lift),
    )


def _room_key_from_display(room_display: str | None, room_display_map: dict[str, str] | None = None) -> str | None:
    if not room_display:
        return None
    if room_display_map is None:
        room_display_map = {
            "Floor1_Large":   "1F Left",
            "Floor1_Small":   "1F Right",
            "Floor2_Small":   "2F Left",
            "Floor2_Large":   "2F Right",
            "Attic":          "Attic",
        }
    for key, display in room_display_map.items():
        if display == room_display:
            return key
    return None


# ── Column indices ───────────────────────────────────────────────────────────

COL_NAME  = 0
COL_AGE   = 1
COL_GEN   = 2
COL_ROOM  = 3
COL_STAT  = 4
COL_BL    = 5
COL_MB    = 6
COL_PIN   = 7
STAT_COLS = list(range(8, 15))   # STR … LCK
COL_SUM   = 15
COL_AGG   = 16
COL_LIB   = 17
COL_INBRD = 18
COL_SEXUALITY = 19
COL_RELNS = 20
COL_REL   = 21
COL_ABIL  = 22
COL_MUTS  = 23
COL_GEN_DEPTH = 24
COL_SRC   = 25
COL_ADV   = 26
COL_TAGS  = 27

# ── Layout widths ────────────────────────────────────────────────────────────

_W_STATUS = 62
_W_STAT   = 34
_W_GEN    = 28
_W_RELNS  = 130
_W_REL    = 68
_W_TRAIT  = 70
_W_TRAIT_NARROW = 56
_ZOOM_MIN = 70
_ZOOM_MAX = 200
_ZOOM_STEP = 10

# ── Stylesheet constants ────────────────────────────────────────────────────

_CHIP_STYLE = ("QLabel { background:#252545; color:#ccc; border-radius:6px;"
               " padding:2px 7px; font-size:11px; }")
_DEFECT_CHIP_STYLE = ("QLabel { background:#3a1a1a; color:#e0a0a0; border-radius:6px;"
                      " padding:2px 7px; font-size:11px; }")
_SEC_STYLE  = "color:#555; font-size:10px; font-weight:bold; letter-spacing:1px;"
_NAME_STYLE = "color:#eee; font-size:13px; font-weight:bold;"
_META_STYLE = "color:#777; font-size:11px;"
_WARN_STYLE = "color:#e07050; font-size:11px; font-weight:bold;"
_SAFE_STYLE = "color:#50c080; font-size:11px;"
_ANCS_STYLE = "color:#aaa; font-size:11px;"
_PANEL_BG   = "background:#0a0a18; border-top:1px solid #1e1e38;"
_DETAIL_TEXT_STYLE = "color:#d7d7e6; font-size:11px;"
_NOTE_STYLE = "color:#666; font-size:10px;"

_SIDEBAR_BTN = """
QPushButton {
    color:#ccc; background:transparent; border:none;
    text-align:left; padding:6px 10px; border-radius:4px; font-size:12px;
}
QPushButton:hover   { background:#252545; }
QPushButton:checked { background:#353568; color:#fff; font-weight:bold; }
"""
