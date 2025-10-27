from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QFileDialog, QGroupBox, QSpinBox, QCheckBox, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt

from pathlib import Path
from typing import List

from ..core.gif_optimizer import optimize_gif_lossy, GifOptimizationError, is_gifsicle_available


class GifOptimizerWidget(QWidget):
    """UI for optimizing GIF size with lossy compression (single or batch)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_files: List[str] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("GIF Optimizer (Lossy)")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)

        desc = QLabel(
            "Reduce GIF size using lossy compression.\n"
            "Set a lossy value (0-200). Higher = smaller file, lower quality."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(desc)

        # Inputs group
        input_group = QGroupBox("1. Select GIFs")
        input_layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add GIFs")
        add_btn.clicked.connect(self.add_gifs)
        btn_row.addWidget(add_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_gifs)
        btn_row.addWidget(clear_btn)
        input_layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)
        input_layout.addWidget(self.list_widget)

        self.count_label = QLabel("No GIFs selected")
        self.count_label.setStyleSheet("color: #666;")
        input_layout.addWidget(self.count_label)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        settings_group = QGroupBox("2. Settings")
        settings_layout = QVBoxLayout()

        # lossy
        lossy_row = QHBoxLayout()
        lossy_row.addWidget(QLabel("Lossy (0-200):"))
        self.lossy_spin = QSpinBox()
        self.lossy_spin.setRange(0, 200)
        self.lossy_spin.setValue(80)
        lossy_row.addWidget(self.lossy_spin)
        settings_layout.addLayout(lossy_row)

        # colors (optional)
        colors_row = QHBoxLayout()
        colors_row.addWidget(QLabel("Max Colors (optional):"))
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, 256)
        self.colors_spin.setSingleStep(2)
        self.colors_spin.setValue(256)
        self.limit_colors_checkbox = QCheckBox("Limit palette")
        self.limit_colors_checkbox.setChecked(False)
        colors_row.addWidget(self.limit_colors_checkbox)
        colors_row.addWidget(self.colors_spin)
        settings_layout.addLayout(colors_row)

        # overwrite option
        overwrite_row = QHBoxLayout()
        self.overwrite_checkbox = QCheckBox("Overwrite originals")
        overwrite_row.addWidget(self.overwrite_checkbox)
        settings_layout.addLayout(overwrite_row)

        # output directory
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Directory:"))
        self.output_dir_edit = QLineEdit()
        out_row.addWidget(self.output_dir_edit, 1)
        browse_out_btn = QPushButton("Browse")
        browse_out_btn.clicked.connect(self.browse_output_dir)
        out_row.addWidget(browse_out_btn)
        settings_layout.addLayout(out_row)

        # gifsicle availability hint
        hint = QLabel(
            "gifsicle " + ("found on PATH" if is_gifsicle_available() else "not found - using Pillow fallback")
        )
        hint.setStyleSheet("color: #888; font-size: 10px;")
        settings_layout.addWidget(hint)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Actions
        actions_row = QHBoxLayout()
        run_single_btn = QPushButton("Optimize First Selected")
        run_single_btn.clicked.connect(self.optimize_single)
        actions_row.addWidget(run_single_btn)

        run_batch_btn = QPushButton("Optimize All")
        run_batch_btn.clicked.connect(self.optimize_batch)
        actions_row.addWidget(run_batch_btn)

        layout.addLayout(actions_row)

        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def add_gifs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select GIF files", "", "GIF Files (*.gif)")
        if files:
            for f in files:
                if f not in self.input_files:
                    self.input_files.append(f)
                    self.list_widget.addItem(f)
            self.update_count()

    def clear_gifs(self):
        self.input_files = []
        self.list_widget.clear()
        self.update_count()

    def browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir_edit.setText(directory)

    def update_count(self):
        n = len(self.input_files)
        self.count_label.setText(f"{n} file(s) selected" if n else "No GIFs selected")

    def _compute_output_path(self, src: str) -> str:
        out_dir = self.output_dir_edit.text().strip()
        overwrite = self.overwrite_checkbox.isChecked()
        if overwrite:
            return src
        if out_dir:
            p = Path(src)
            return str(Path(out_dir) / (p.stem + "-optimized.gif"))
        return ""  # signal to optimizer to choose default alongside

    def _get_colors(self) -> int | None:
        return self.colors_spin.value() if self.limit_colors_checkbox.isChecked() else None

    def optimize_single(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "No GIF selected")
            return
        self.optimize_paths([self.input_files[0]])

    def optimize_batch(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "No GIFs to process")
            return
        self.optimize_paths(self.input_files)

    def optimize_paths(self, paths: List[str]):
        lossy = self.lossy_spin.value()
        colors = self._get_colors()
        overwrite = self.overwrite_checkbox.isChecked()
        success = 0
        failed: List[str] = []
        for src in paths:
            out_path = self._compute_output_path(src)
            # normalize: if empty string, pass None to let optimizer decide default
            if out_path == "":
                out_path = None
            try:
                result = optimize_gif_lossy(
                    input_path=src,
                    output_path=out_path,
                    lossy=lossy,
                    colors=colors,
                    overwrite=overwrite,
                )
                success += 1
                self.status_label.setText(f"Optimized: {Path(result).name}")
            except GifOptimizationError as e:
                failed.append(f"{Path(src).name}: {str(e)}")

        if failed:
            QMessageBox.warning(self, "Completed with errors", "\n".join(failed))
        else:
            QMessageBox.information(self, "Success", f"Optimized {success} file(s)")


