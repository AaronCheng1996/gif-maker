"""
Settings Dialog
===============
Accessible via the "Settings" menu in the main menu bar.
Currently exposes language selection; ready to host future options.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QGroupBox, QSpacerItem,
    QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt

from ..i18n import tr, get_language, get_available_languages, set_language
from .. import settings as AppSettings


class SettingsDialog(QDialog):
    """Application settings dialog (language and future options)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Application Settings"))
        self.setMinimumWidth(380)
        self.setModal(True)
        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)

        # ── Language group ─────────────────────────────────────────────────
        lang_group = QGroupBox(tr("Language Settings"))
        lang_layout = QVBoxLayout(lang_group)
        lang_layout.setContentsMargins(12, 16, 12, 12)
        lang_layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Interface Language:")))

        self._lang_combo = QComboBox()
        current = get_language()
        for idx, (code, display) in enumerate(get_available_languages()):
            self._lang_combo.addItem(display, code)
            if code == current:
                self._lang_combo.setCurrentIndex(idx)
        row.addWidget(self._lang_combo)
        row.addStretch()
        lang_layout.addLayout(row)

        hint = QLabel(tr("Restart to apply language change"))
        hint.setStyleSheet("font-size: 11px; color: #8a95b8;")
        lang_layout.addWidget(hint)

        root.addWidget(lang_group)

        # ── Separator ──────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2e3148;")
        root.addWidget(sep)

        # ── Dialog buttons ─────────────────────────────────────────────────
        root.addSpacerItem(
            QSpacerItem(0, 4, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.setFixedWidth(88)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton(tr("OK"))
        self._ok_btn.setFixedWidth(88)
        self._ok_btn.setDefault(True)
        self._ok_btn.setStyleSheet(
            f"background-color: #4d86f0; color: #ffffff; border: none; "
            f"border-radius: 4px; font-weight: 600;"
        )
        self._ok_btn.clicked.connect(self._apply_and_accept)
        btn_row.addWidget(self._ok_btn)

        root.addLayout(btn_row)

    # ──────────────────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────────────────

    def _apply_and_accept(self) -> None:
        selected_code: str = self._lang_combo.currentData()
        if selected_code != get_language():
            set_language(selected_code)
            AppSettings.set("language", selected_code)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                tr("Settings"),
                tr("Restart to apply language change"),
            )
        self.accept()
