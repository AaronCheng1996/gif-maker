"""
GIF Maker – Minimal Harmonious Dark Theme
==========================================
Single source of truth for colors and the global Qt stylesheet.

Design intent: neutral near-black backgrounds, a single blue accent family,
consistent 4 px radius, and subdued typography that stays out of the way.

Usage (in main.py):
    from .widgets.theme import AppTheme
    app = QApplication(sys.argv)
    AppTheme.apply(app)
"""
from PyQt6.QtWidgets import QApplication


class AppTheme:
    # ── Palette ──────────────────────────────────────────────────────────────
    # Backgrounds (neutral, low-saturation dark)
    BG          = "#16181f"   # main window / dialog background
    PANEL       = "#1c1e27"   # left/right panels
    CARD        = "#22242f"   # cards, groupboxes, list backgrounds
    ELEVATED    = "#282b38"   # headers, raised surfaces
    INPUT_BG    = "#181a23"   # text inputs, spinboxes, combos

    # Borders (single family, subtle)
    BORDER      = "#2e3148"   # default border
    BORDER_MID  = "#404568"   # mid-emphasis border
    BORDER_FOCUS= "#4d86f0"   # focus / selection accent

    # Text
    TEXT        = "#e6eaf6"   # primary text
    TEXT_DIM    = "#8a95b8"   # secondary / muted
    TEXT_HINT   = "#434866"   # placeholder / hint

    # Accents (single blue family)
    ACCENT      = "#4d86f0"   # blue – links, focus, selection
    ACCENT_DARK = "#3a6cd4"   # darker blue (pressed states)
    SUCCESS     = "#4caf7a"   # green
    WARNING     = "#e6a23c"   # amber
    ERROR       = "#d95757"   # red
    STAR        = "#e6a23c"   # gold star

    # Buttons
    BTN_BG      = "#282b38"
    BTN_HOVER   = "#323647"
    BTN_BORDER  = "#404568"
    BTN_PRESSED = "#1e2030"

    # Selection
    SEL_BG      = "#1f3055"   # list / table selection background

    # Special group UI (harmonized to blue accent family)
    GRP_HEADER_SEL   = "#1c3359"
    GRP_HEADER_DEF   = "#22253a"
    GRP_BORDER_SEL   = "#4d86f0"
    GRP_BORDER_DEF   = "#2e3148"
    LB_BORDER        = "#4d86f0"
    LB_HEADER        = "#1a2038"
    LB_LABEL         = "#a0baf0"
    TL_BG            = "#181a23"
    TL_BORDER        = "#2e3148"
    TL_LABEL         = "#a0baf0"
    SLOT_BG          = "#13151e"
    SLOT_BORDER      = "#282b38"
    FRAME_ROW_BG     = "#1e2230"
    FRAME_ROW_BORDER = "#2e3148"
    THUMB_BG         = "#0e0f14"
    THUMB_BORDER     = "#404568"
    MAT_NAME         = "#9aafc8"
    CLONE_BTN        = "#7aabf0"
    SEP_COLOR        = "#282b38"

    # ── Global Stylesheet ────────────────────────────────────────────────────
    QSS = f"""
/* ── Foundations ─────────────────────────────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {BG};
    color: {TEXT};
}}
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 12px;
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
}}
QFrame {{
    background-color: transparent;
}}

/* ── Labels ──────────────────────────────────────────────────────────────── */
QLabel {{
    color: {TEXT};
    background-color: transparent;
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BTN_BG};
    color: {TEXT};
    border: 1px solid {BTN_BORDER};
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {BTN_HOVER};
    border-color: {BORDER_MID};
}}
QPushButton:pressed {{
    background-color: {BTN_PRESSED};
    border-color: {BORDER_FOCUS};
}}
QPushButton:disabled {{
    background-color: {BG};
    color: {TEXT_HINT};
    border-color: {BORDER};
}}

/* ── Text inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {BORDER_FOCUS};
}}
QLineEdit:disabled {{
    color: {TEXT_HINT};
    background-color: {BG};
}}

/* ── Spinboxes ───────────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {ACCENT};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {BORDER_FOCUS};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {BTN_BG};
    border: none;
    border-left: 1px solid {BORDER};
    width: 18px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {BTN_HOVER};
}}

/* ── ComboBox ────────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {SEL_BG};
    min-height: 24px;
}}
QComboBox:hover {{
    border-color: {BORDER_MID};
}}
QComboBox:focus {{
    border-color: {BORDER_FOCUS};
}}
QComboBox::drop-down {{
    border-left: 1px solid {BORDER};
    background-color: {BTN_BG};
    width: 22px;
    border-radius: 0 4px 4px 0;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {SEL_BG};
    selection-color: {TEXT};
    outline: none;
    padding: 2px;
}}

/* ── Lists ───────────────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {SEL_BG};
    selection-color: {TEXT};
    outline: none;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {BORDER};
}}
QListWidget::item:last-child {{
    border-bottom: none;
}}
QListWidget::item:hover {{
    background-color: {ELEVATED};
}}
QListWidget::item:selected {{
    background-color: {SEL_BG};
    color: {TEXT};
}}

/* ── Table ───────────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    gridline-color: {BORDER};
    selection-background-color: {SEL_BG};
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px;
}}
QTableWidget::item:hover {{
    background-color: {ELEVATED};
}}
QTableWidget::item:selected {{
    background-color: {SEL_BG};
}}
QHeaderView::section {{
    background-color: {ELEVATED};
    color: {TEXT_DIM};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}}
QHeaderView::section:first {{
    border-left: none;
}}

/* ── GroupBox ────────────────────────────────────────────────────────────── */
QGroupBox {{
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {TEXT_DIM};
    background-color: {BG};
    text-transform: uppercase;
}}

/* ── TabWidget ───────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-top: none;
    background-color: {BG};
}}
QTabBar {{
    background-color: {PANEL};
    border-bottom: 1px solid {BORDER};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_DIM};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    margin-right: 1px;
    font-size: 12px;
    min-width: 100px;
}}
QTabBar::tab:hover {{
    color: {TEXT};
    border-bottom: 2px solid {BORDER_MID};
    background-color: {ELEVATED};
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
    background-color: {BG};
}}
QTabBar::tab:disabled {{
    color: {TEXT_HINT};
}}

/* ── Scrollbars ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER_MID};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {BORDER_MID};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::corner {{
    background-color: transparent;
}}

/* ── CheckBox ────────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT};
    spacing: 6px;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BTN_BORDER};
    border-radius: 3px;
    background-color: {INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:disabled {{
    background-color: {BG};
    border-color: {BORDER};
}}

/* ── RadioButton ─────────────────────────────────────────────────────────── */
QRadioButton {{
    color: {TEXT};
    spacing: 6px;
    background-color: transparent;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BTN_BORDER};
    border-radius: 7px;
    background-color: {INPUT_BG};
}}
QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── ProgressBar ─────────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT};
    text-align: center;
    font-size: 11px;
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}

/* ── Splitter ────────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QSplitter::handle:hover {{
    background-color: {ACCENT};
}}

/* ── ScrollArea ──────────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* ── Menu ────────────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {PANEL};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
    spacing: 0;
    padding: 2px 4px;
}}
QMenuBar::item {{
    padding: 5px 12px;
    background-color: transparent;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {BTN_BG};
    color: {TEXT};
}}
QMenu {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px 6px 16px;
    border-radius: 3px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background-color: {SEL_BG};
    color: {TEXT};
}}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 8px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER_MID};
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 11px;
}}

/* ── Slider ──────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {ACCENT};
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

/* ── StatusBar ───────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {PANEL};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
QStatusBar QLabel {{
    color: {TEXT_DIM};
    padding: 0 8px;
    font-size: 11px;
}}
"""

    @classmethod
    def apply(cls, app: QApplication) -> None:
        """Apply Fusion palette + the minimal dark QSS to the application."""
        app.setStyle("Fusion")
        app.setStyleSheet(cls.QSS)
