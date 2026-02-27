"""
GIF Maker – Unified Dark Theme
===============================
Single source of truth for colors and the global Qt stylesheet.

Usage (in main.py):
    from .widgets.theme import AppTheme
    app = QApplication(sys.argv)
    AppTheme.apply(app)
"""
from PyQt6.QtWidgets import QApplication


class AppTheme:
    # ── Palette ──────────────────────────────────────────────────────────────
    # Backgrounds
    BG          = "#1a1d27"   # main window / dialog background
    PANEL       = "#21253a"   # left/right panels
    CARD        = "#282d3d"   # cards, groupboxes, list backgrounds
    ELEVATED    = "#2e3347"   # headers, raised surfaces
    INPUT_BG    = "#1e2233"   # text inputs, spinboxes, combos

    # Borders
    BORDER      = "#383d52"   # default border
    BORDER_MID  = "#4a5266"   # mid-emphasis border
    BORDER_FOCUS= "#4a9eff"   # focus / selection accent

    # Text
    TEXT        = "#e4e8f4"   # primary text
    TEXT_DIM    = "#9ba8c0"   # secondary / muted
    TEXT_HINT   = "#56607a"   # placeholder / hint

    # Accents
    ACCENT      = "#4a9eff"   # blue – links, focus, selection
    ACCENT_DARK = "#2563eb"   # darker blue
    SUCCESS     = "#56b374"   # green
    WARNING     = "#f0a832"   # amber
    ERROR       = "#e05560"   # red
    STAR        = "#f0a832"   # gold star

    # Buttons
    BTN_BG      = "#363c51"
    BTN_HOVER   = "#424a62"
    BTN_BORDER  = "#525b73"
    BTN_PRESSED = "#2a2f40"

    # Selection
    SEL_BG      = "#2a3a5a"   # list / table selection background

    # Special group UI colors (kept from original design)
    GRP_HEADER_SEL   = "#1e3a5f"
    GRP_HEADER_DEF   = "#252b3a"
    GRP_BORDER_SEL   = "#4a9eff"
    GRP_BORDER_DEF   = "#3b4252"
    LB_BORDER        = "#7b5ea7"
    LB_HEADER        = "#2a1f3d"
    LB_LABEL         = "#d0c0ff"
    TL_BG            = "#1e1a2a"
    TL_BORDER        = "#4a4060"
    TL_LABEL         = "#c0a0ff"
    SLOT_BG          = "#161220"
    SLOT_BORDER      = "#3a3550"
    FRAME_ROW_BG     = "#232a35"
    FRAME_ROW_BORDER = "#3b4252"
    THUMB_BG         = "#111111"
    THUMB_BORDER     = "#555555"
    MAT_NAME         = "#b0bec5"
    CLONE_BTN        = "#88c0d0"
    SEP_COLOR        = "#3d4466"

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
}}
QPushButton:disabled {{
    background-color: #262b3a;
    color: {TEXT_HINT};
    border-color: {BORDER};
}}

/* ── Text inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {BORDER_FOCUS};
}}
QLineEdit:disabled {{
    color: {TEXT_HINT};
    background-color: #1c2030;
}}

/* ── Spinboxes ───────────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 2px 4px;
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
    width: 16px;
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
    border-radius: 3px;
    padding: 3px 8px;
    selection-background-color: {SEL_BG};
    min-height: 22px;
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
    border-radius: 0 3px 3px 0;
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
    border-radius: 3px;
    selection-background-color: {SEL_BG};
    selection-color: {TEXT};
    outline: none;
}}
QListWidget::item {{
    padding: 4px 6px;
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
    padding: 3px;
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
    padding: 4px 6px;
    font-weight: bold;
    font-size: 11px;
}}
QHeaderView::section:first {{
    border-left: none;
}}

/* ── GroupBox ────────────────────────────────────────────────────────────── */
QGroupBox {{
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 5px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {TEXT_DIM};
    background-color: {BG};
}}

/* ── TabWidget ───────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {BG};
    border-radius: 0 4px 4px 4px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {PANEL};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 6px 16px;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
    font-size: 12px;
}}
QTabBar::tab:hover {{
    background-color: {ELEVATED};
    color: {TEXT};
}}
QTabBar::tab:selected {{
    background-color: {BG};
    color: {ACCENT};
    border-bottom-color: {BG};
    font-weight: bold;
}}
QTabBar::tab:disabled {{
    color: {TEXT_HINT};
}}

/* ── Scrollbars ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: {BG};
    width: 10px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {BTN_BG};
    border-radius: 5px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {BTN_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: {BG};
    height: 10px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {BTN_BG};
    border-radius: 5px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {BTN_HOVER};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::corner {{
    background-color: {BG};
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
    border-color: {BORDER_MID};
}}
QCheckBox::indicator:disabled {{
    background-color: #1c2030;
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
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
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
    spacing: 2px;
    padding: 2px 4px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    background-color: transparent;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background-color: {BTN_BG};
}}
QMenu {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 24px 5px 16px;
}}
QMenu::item:selected {{
    background-color: {SEL_BG};
    color: {TEXT};
}}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 3px 8px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER_MID};
    padding: 4px 8px;
    border-radius: 3px;
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

/* ── StatusBar / message areas ───────────────────────────────────────────── */
QStatusBar {{
    background-color: {PANEL};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}
"""

    @classmethod
    def apply(cls, app: QApplication) -> None:
        """Apply Fusion palette + the dark QSS to the application."""
        app.setStyle("Fusion")
        app.setStyleSheet(cls.QSS)
