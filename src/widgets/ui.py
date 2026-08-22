"""Shared layout metrics and label styles for the tool tabs.

Every tab had been choosing its own margins, spacing and label sizes, so moving
between them shifted the padding and changed how a heading looked — fourteen
different margin settings and six font sizes across the widget layer. The values
here are the ones the older tabs had converged on; the point of naming them is
that a new tab picks them up instead of inventing another set.

Colours stay in `theme.py`; this module is only about size and rhythm.
"""
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import AppTheme as _T

# ── spacing scale ────────────────────────────────────────────────────────
# One step (4px) between related controls, two between groups.
GAP_TIGHT = 4        # rows inside a group box
GAP = 8              # between controls in a panel
MARGIN_PANEL = 8     # inside a panel that sits in a splitter
MARGIN_GROUP = 8     # inside a QGroupBox

# ── type scale ───────────────────────────────────────────────────────────
FONT_TITLE = 14      # the one heading at the top of a panel
FONT_SECTION = 12    # a heading within a panel
FONT_BODY = 11       # readouts and status lines
FONT_HINT = 10       # explanatory small print


# ── shared stylesheets ───────────────────────────────────────────────────
# Two title styles had grown up side by side — `bold 15px #e4e8f4` in the older
# tabs and `600 14px` in the newer ones, on two slightly different whites — so
# the heading changed shape when you switched tab.
TITLE_QSS = (f"font-weight: 600; font-size: {FONT_TITLE}px; "
             f"color: {_T.TEXT}; padding: 2px 0;")

SECTION_QSS = (f"font-weight: 600; font-size: {FONT_SECTION}px; color: {_T.TEXT_DIM};")
BODY_QSS = f"color: {_T.TEXT_DIM}; font-size: {FONT_BODY}px;"
HINT_QSS = f"color: {_T.TEXT_HINT}; font-size: {FONT_HINT}px;"

# The one green button a tab ends with.
GO_QSS = (f"QPushButton {{ font-weight: 600; font-size: {FONT_SECTION}px; "
          f"background-color: {_T.GO_BG}; color: {_T.GO_TEXT}; "
          f"border: 1px solid {_T.GO_BORDER}; border-radius: 4px; padding: 6px 14px; }}"
          f"QPushButton:disabled {{ color: {_T.TEXT_HINT}; "
          f"background-color: {_T.BTN_BG}; border-color: {_T.BTN_BORDER}; }}")


def tab_layout(widget: QWidget, horizontal: bool = True):
    """Outer layout of a tab: no margin, because it only holds a splitter.

    A splitter draws its own handles right to the edge, and an outer margin
    leaves a dead border that does not line up with the panels inside it."""
    layout = QHBoxLayout(widget) if horizontal else QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return layout


def panel_layout(widget: QWidget) -> QVBoxLayout:
    """Layout for one panel of a splitter."""
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(MARGIN_PANEL, MARGIN_PANEL, MARGIN_PANEL, MARGIN_PANEL)
    layout.setSpacing(GAP)
    return layout


def group_layout(vertical: bool = True):
    """Layout for the inside of a QGroupBox."""
    layout = QVBoxLayout() if vertical else QHBoxLayout()
    layout.setContentsMargins(MARGIN_GROUP, MARGIN_GROUP, MARGIN_GROUP, MARGIN_GROUP)
    layout.setSpacing(GAP_TIGHT)
    return layout


def row_layout():
    """A horizontal run of controls that belong together."""
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(GAP_TIGHT)
    return layout


def title_label(text: str) -> QLabel:
    """The single heading at the top of a panel."""
    label = QLabel(text)
    label.setStyleSheet(TITLE_QSS)
    return label


def section_label(text: str) -> QLabel:
    """A heading for a group of controls within a panel."""
    label = QLabel(text)
    label.setStyleSheet(SECTION_QSS)
    return label


def body_label(text: str = "") -> QLabel:
    """A readout or status line. Wraps, because these carry file paths."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(BODY_QSS)
    return label


def primary_button(text: str) -> "QPushButton":
    """The one button a tab ends with: Convert, Crop, Export.

    Three tabs had spelled this out by hand in slightly different words; there
    should be exactly one green button per tab and it should look the same in
    all of them."""
    from PyQt6.QtWidgets import QPushButton

    button = QPushButton(text)
    button.setStyleSheet(GO_QSS)
    return button


def hint_label(text: str = "") -> QLabel:
    """Small print explaining a control."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(HINT_QSS)
    return label
