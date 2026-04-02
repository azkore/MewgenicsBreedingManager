"""Font enforcement, widget tree styling, and UI helper widgets."""
import re
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QPushButton,
    QTableWidget, QTableView, QHeaderView,
)
from PySide6.QtGui import QColor

from mewgenics.constants import (
    _CHIP_STYLE, _DEFECT_CHIP_STYLE, _SEC_STYLE, _DETAIL_TEXT_STYLE, _SIDEBAR_BTN,
)


_ACCESSIBILITY_MIN_FONT_PX = 12
_ACCESSIBILITY_MIN_FONT_PT = 10.0
_FONT_SIZE_RE = re.compile(r"(font-size\s*:\s*)(\d+)(px)")


def _with_min_font_px(stylesheet: str, min_px: int = _ACCESSIBILITY_MIN_FONT_PX) -> str:
    """Clamp stylesheet font-size declarations to an accessible minimum."""
    if not stylesheet or "font-size" not in stylesheet:
        return stylesheet
    return _FONT_SIZE_RE.sub(
        lambda m: f"{m.group(1)}{max(min_px, int(m.group(2)))}{m.group(3)}",
        stylesheet,
    )


def _enforce_min_font_in_widget_tree(root: Optional[QWidget], min_px: int = _ACCESSIBILITY_MIN_FONT_PX):
    """Apply minimum stylesheet font size to a widget and all descendants."""
    if root is None:
        return
    from mewgenics.utils.table_state import _configure_table_view_behavior
    widgets = [root] + root.findChildren(QWidget)
    for widget in widgets:
        style = widget.styleSheet()
        if style and "font-size" in style:
            adjusted = _with_min_font_px(style, min_px=min_px)
            if adjusted != style:
                widget.setStyleSheet(adjusted)
        _configure_table_view_behavior(widget)


def _apply_font_offset_to_tree(root: Optional[QWidget], offset_px: int):
    """
    Walk the widget tree and adjust every hardcoded `font-size:Npx` in
    stylesheets by `offset_px`.
    """
    if root is None:
        return
    min_px = max(8, _ACCESSIBILITY_MIN_FONT_PX + offset_px)
    for widget in [root] + root.findChildren(QWidget):
        style = widget.styleSheet()
        if not style or "font-size" not in style:
            continue
        orig = widget.property("_orig_ss")
        if orig is None:
            widget.setProperty("_orig_ss", style)
            orig = style
        new_style = _FONT_SIZE_RE.sub(
            lambda m, _off=offset_px, _min=min_px: (
                f"{m.group(1)}{max(_min, int(m.group(2)) + _off)}{m.group(3)}"
            ),
            orig,
        ) if offset_px != 0 else orig
        if new_style != style:
            widget.setStyleSheet(new_style)


def _enable_manual_header_resize(header, columns: list[int]):
    """Keep current default widths but allow the user to drag-resize columns."""
    for col in columns:
        header.setSectionResizeMode(col, QHeaderView.Interactive)


# ── Widget factories ─────────────────────────────────────────────────────────

def _chip(text: str, tooltip: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_CHIP_STYLE)
    if tooltip:
        lbl.setToolTip(tooltip)
    return lbl


def _defect_chip(text: str, tooltip: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_DEFECT_CHIP_STYLE)
    if tooltip:
        lbl.setToolTip(tooltip)
    return lbl


def _sec(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SEC_STYLE)
    return lbl


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#1e1e38;")
    return f


def _hsep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color:#1e1e38; margin:6px 0;")
    return f


def _sidebar_btn(label: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setStyleSheet(_SIDEBAR_BTN)
    return btn


def _high_contrast_stylesheet() -> str:
    """Return a high-contrast stylesheet overlay for accessibility presets."""
    return """
        QWidget {
            color: #f4f6ff;
        }
        QDialog, QMainWindow, QMenu {
            background: #05050b;
        }
        QLabel {
            color: #f4f6ff;
        }
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background: #05050b;
            color: #ffffff;
            border: 1px solid #ffd34d;
            selection-background-color: #0057d9;
            selection-color: #ffffff;
        }
        QTableView, QTableWidget {
            background: #05050b;
            color: #ffffff;
            gridline-color: #707070;
            selection-background-color: #0057d9;
            selection-color: #ffffff;
        }
        QHeaderView::section {
            background: #14142a;
            color: #ffffff;
            border: 1px solid #ffd34d;
        }
        QPushButton, QToolButton {
            background: #14142a;
            color: #ffffff;
            border: 1px solid #ffd34d;
        }
        QPushButton:hover, QToolButton:hover {
            background: #20203c;
        }
        QGroupBox {
            border: 1px solid #ffd34d;
            color: #ffffff;
            margin-top: 12px;
        }
        QScrollBar:vertical, QScrollBar:horizontal {
            background: #05050b;
        }
        QMenu::item:selected {
            background: #0057d9;
        }
    """


def _detail_text_block(lines: list[str], style: str = _DETAIL_TEXT_STYLE) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 2, 0, 0)
    layout.setSpacing(4)
    for line in lines:
        lbl = QLabel(line)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(style)
        layout.addWidget(lbl)
    return box


def _blend_qcolor(base: QColor, target: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, float(ratio)))
    return QColor(
        round(base.red() + (target.red() - base.red()) * ratio),
        round(base.green() + (target.green() - base.green()) * ratio),
        round(base.blue() + (target.blue() - base.blue()) * ratio),
    )
