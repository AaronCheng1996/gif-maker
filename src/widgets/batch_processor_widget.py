"""
Batch Processor Widget - UI for automated batch GIF generation

Allows users to:
1. Select multiple images
2. Choose a template
3. Configure tile split settings
4. Process all images automatically
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QComboBox, QProgressBar,
                              QRadioButton, QButtonGroup, QScrollArea, QGridLayout,
                              QCheckBox, QLineEdit, QSplitter)
from PyQt6.QtCore import pyqtSignal, Qt, QObject, QThread
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from .theme import AppTheme as _T


class _BatchWorker(QObject):
    """Runs BatchProcessor.process_batch in a background thread."""

    progress = pyqtSignal(int, int, str)          # current, total, message
    finished = pyqtSignal(list, list)             # successful, failed

    def __init__(self, processor, kwargs: dict):
        super().__init__()
        self._processor = processor
        self._kwargs = kwargs

    def run(self):
        try:
            successful, failed = self._processor.process_batch(**self._kwargs)
        except Exception as e:
            successful, failed = [], [("", str(e))]
        self.finished.emit(successful, failed)


class BatchProcessorWidget(QWidget):
    """
    Widget for batch processing images into GIFs
    """
    
    # Signal emitted when batch processing completes
    batch_complete = pyqtSignal(int, int)  # (successful_count, failed_count)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.image_paths: List[str] = []
        self.selected_template: Optional[Dict[str, Any]] = None
        self.selected_template_name: str = ""
        self.selected_positions: List[Tuple[int, int]] = []
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Title
        title_label = QLabel("Batch GIF Generator")
        title_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Automatically split images into tiles and generate GIFs using a template.\n"
            "Each image will be processed: split → apply template → export as GIF."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # === Image Selection Section ===
        image_group = QGroupBox("1. Select Images")
        image_layout = QVBoxLayout()
        
        image_buttons = QHBoxLayout()
        self.add_images_btn = QPushButton("Add Images")
        self.add_images_btn.clicked.connect(self.add_images)
        image_buttons.addWidget(self.add_images_btn)
        
        self.clear_images_btn = QPushButton("Clear All")
        self.clear_images_btn.clicked.connect(self.clear_images)
        image_buttons.addWidget(self.clear_images_btn)
        
        image_layout.addLayout(image_buttons)
        
        self.image_list = QListWidget()
        self.image_list.setMaximumHeight(120)
        self.image_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        image_layout.addWidget(self.image_list)
        
        self.image_count_label = QLabel("No images selected")
        self.image_count_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        image_layout.addWidget(self.image_count_label)
        
        image_group.setLayout(image_layout)
        layout.addWidget(image_group)
        
        # === Template Selection Section ===
        template_group = QGroupBox("2. Select Template")
        template_layout = QVBoxLayout()
        
        template_select_layout = QHBoxLayout()
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        template_select_layout.addWidget(QLabel("Template:"))
        template_select_layout.addWidget(self.template_combo, stretch=1)
        
        self.refresh_templates_btn = QPushButton("Refresh")
        self.refresh_templates_btn.clicked.connect(self.refresh_templates)
        self.refresh_templates_btn.setMaximumWidth(80)
        template_select_layout.addWidget(self.refresh_templates_btn)
        
        template_layout.addLayout(template_select_layout)
        
        self.template_info_label = QLabel("No template selected")
        self.template_info_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        self.template_info_label.setWordWrap(True)
        template_layout.addWidget(self.template_info_label)
        
        template_group.setLayout(template_layout)
        layout.addWidget(template_group)
        
        # === Split Settings Section ===
        split_group = QGroupBox("3. Tile Split Settings")
        split_layout = QVBoxLayout()
        split_layout.setSpacing(8)
        
        # Split mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Split Mode:"))
        
        self.split_mode_group = QButtonGroup()
        self.grid_mode_radio = QRadioButton("Grid (rows × cols)")
        self.size_mode_radio = QRadioButton("Size (tile dimensions)")
        self.grid_mode_radio.setChecked(True)
        self.split_mode_group.addButton(self.grid_mode_radio, 0)
        self.split_mode_group.addButton(self.size_mode_radio, 1)
        
        self.grid_mode_radio.toggled.connect(self.on_split_mode_changed)
        
        mode_layout.addWidget(self.grid_mode_radio)
        mode_layout.addWidget(self.size_mode_radio)
        mode_layout.addStretch()
        split_layout.addLayout(mode_layout)
        
        # Grid settings
        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("Grid:"))
        
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setMinimum(1)
        self.rows_spinbox.setMaximum(100)
        self.rows_spinbox.setValue(4)
        self.rows_spinbox.setMaximumWidth(80)
        self.rows_spinbox.valueChanged.connect(self.update_position_selector)
        grid_layout.addWidget(self.rows_spinbox)
        
        grid_layout.addWidget(QLabel("×"))
        
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setMinimum(1)
        self.cols_spinbox.setMaximum(100)
        self.cols_spinbox.setValue(4)
        self.cols_spinbox.setMaximumWidth(80)
        self.cols_spinbox.valueChanged.connect(self.update_position_selector)
        grid_layout.addWidget(self.cols_spinbox)
        
        grid_layout.addStretch()
        split_layout.addLayout(grid_layout)
        
        # Size settings
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Tile Size:"))
        
        self.tile_width_spinbox = QSpinBox()
        self.tile_width_spinbox.setMinimum(1)
        self.tile_width_spinbox.setMaximum(10000)
        self.tile_width_spinbox.setValue(32)
        self.tile_width_spinbox.setMaximumWidth(80)
        size_layout.addWidget(self.tile_width_spinbox)
        
        size_layout.addWidget(QLabel("×"))
        
        self.tile_height_spinbox = QSpinBox()
        self.tile_height_spinbox.setMinimum(1)
        self.tile_height_spinbox.setMaximum(10000)
        self.tile_height_spinbox.setValue(32)
        self.tile_height_spinbox.setMaximumWidth(80)
        size_layout.addWidget(self.tile_height_spinbox)
        
        size_layout.addStretch()
        split_layout.addLayout(size_layout)
        
        # Position selector
        position_label = QLabel("Select Tile Positions to Keep:")
        position_label.setStyleSheet("font-weight: bold; margin-top: 5px; font-size: 12px;")
        split_layout.addWidget(position_label)
        
        position_controls = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_positions)
        self.select_all_btn.setMaximumHeight(25)
        position_controls.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all_positions)
        self.deselect_all_btn.setMaximumHeight(25)
        position_controls.addWidget(self.deselect_all_btn)
        position_controls.addStretch()
        
        split_layout.addLayout(position_controls)
        
        # Position grid (scrollable)
        position_scroll = QScrollArea()
        position_scroll.setWidgetResizable(True)
        position_scroll.setMaximumHeight(150)
        
        self.position_grid_widget = QWidget()
        self.position_grid_layout = QGridLayout()
        self.position_grid_widget.setLayout(self.position_grid_layout)
        position_scroll.setWidget(self.position_grid_widget)
        
        split_layout.addWidget(position_scroll)
        
        split_group.setLayout(split_layout)
        layout.addWidget(split_group)
        
        # === Output Settings Section ===
        output_group = QGroupBox("4. Output Settings")
        output_layout = QVBoxLayout()
        
        # Output size setting
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Output Size:"))
        
        self.output_width_spinbox = QSpinBox()
        self.output_width_spinbox.setMinimum(1)
        self.output_width_spinbox.setMaximum(10000)
        self.output_width_spinbox.setValue(200)
        self.output_width_spinbox.setMaximumWidth(80)
        size_layout.addWidget(self.output_width_spinbox)
        
        size_layout.addWidget(QLabel("×"))
        
        self.output_height_spinbox = QSpinBox()
        self.output_height_spinbox.setMinimum(1)
        self.output_height_spinbox.setMaximum(10000)
        self.output_height_spinbox.setValue(256)
        self.output_height_spinbox.setMaximumWidth(80)
        size_layout.addWidget(self.output_height_spinbox)
        
        size_layout.addStretch()
        output_layout.addLayout(size_layout)
        
        # Color palette setting
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color Palette:"))
        self.color_palette_combo = QComboBox()
        self.color_palette_combo.addItems(["256", "128", "64", "32", "16"])
        self.color_palette_combo.setCurrentText("256")
        color_layout.addWidget(self.color_palette_combo)
        color_layout.addStretch()
        output_layout.addLayout(color_layout)
        
        self.same_dir_checkbox = QCheckBox("Save GIFs in same directory as source images")
        self.same_dir_checkbox.setChecked(True)
        self.same_dir_checkbox.toggled.connect(self.on_output_mode_changed)
        output_layout.addWidget(self.same_dir_checkbox)
        
        custom_dir_layout = QHBoxLayout()
        custom_dir_layout.addWidget(QLabel("Output Directory:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setEnabled(False)
        self.output_dir_edit.setPlaceholderText("Select custom output directory...")
        custom_dir_layout.addWidget(self.output_dir_edit, stretch=1)
        
        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.setEnabled(False)
        self.browse_output_btn.clicked.connect(self.browse_output_directory)
        self.browse_output_btn.setMaximumWidth(80)
        custom_dir_layout.addWidget(self.browse_output_btn)
        
        output_layout.addLayout(custom_dir_layout)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # === Validation Info ===
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet(
            f"padding: 5px; border-radius: 3px; color: {_T.TEXT_DIM}; font-size: 11px;"
        )
        layout.addWidget(self.validation_label)
        
        # === Progress Section ===
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Ready to process")
        self.progress_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        progress_layout.addWidget(self.progress_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # === Action Buttons ===
        action_layout = QHBoxLayout()
        
        self.validate_btn = QPushButton("Validate Settings")
        self.validate_btn.clicked.connect(self.validate_settings)
        action_layout.addWidget(self.validate_btn)
        
        self.process_btn = QPushButton("Start Batch Processing")
        self.process_btn.clicked.connect(self.start_batch_processing)
        self.process_btn.setStyleSheet(
            f"font-weight: bold; font-size: 13px; padding: 8px 20px; "
            f"background-color: {_T.ACCENT_DARK}; color: white; "
            f"border: 1px solid {_T.ACCENT}; border-radius: 4px;"
        )
        action_layout.addWidget(self.process_btn)
        
        layout.addLayout(action_layout)
        
        layout.addStretch()

        # ── Column 1: controls in a scroll area (320 px — same as Material Library) ──
        left_widget = QWidget()
        left_widget.setLayout(layout)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(240)

        # ── Column 2: tile grid preview ───────────────────────────────────────
        from .tile_editor import TilePreviewWidget
        tile_col = QWidget()
        tile_col_layout = QVBoxLayout(tile_col)
        tile_col_layout.setContentsMargins(4, 4, 4, 4)
        tile_lbl = QLabel("Tile Preview")
        tile_lbl.setStyleSheet("font-size: 11px; color: #9ba8c0;")
        tile_col_layout.addWidget(tile_lbl)
        self.batch_tile_preview = TilePreviewWidget()
        tile_col_layout.addWidget(self.batch_tile_preview)

        # ── Column 3: GIF animation preview ──────────────────────────────────
        from .preview_widget import PreviewWidget
        gif_col = QWidget()
        gif_col_layout = QVBoxLayout(gif_col)
        gif_col_layout.setContentsMargins(4, 4, 4, 4)
        anim_lbl = QLabel("GIF Preview  (click to generate)")
        anim_lbl.setStyleSheet("font-size: 11px; color: #9ba8c0;")
        gif_col_layout.addWidget(anim_lbl)
        self._gen_preview_btn = QPushButton("▶  Generate GIF Preview (first image)")
        self._gen_preview_btn.setEnabled(False)
        self._gen_preview_btn.clicked.connect(self._generate_gif_preview)
        gif_col_layout.addWidget(self._gen_preview_btn)
        self.batch_preview_widget = PreviewWidget()
        gif_col_layout.addWidget(self.batch_preview_widget)

        # ── 3-column splitter ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(tile_col)
        splitter.addWidget(gif_col)
        splitter.setSizes([320, 640, 640])

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self.setLayout(outer)

        # Wire image list selection → tile preview
        self.image_list.currentRowChanged.connect(self._on_image_list_row_changed)
        # Wire grid settings → tile preview
        self.rows_spinbox.valueChanged.connect(self._update_tile_preview_grid)
        self.cols_spinbox.valueChanged.connect(self._update_tile_preview_grid)

        # Initialize
        self.update_position_selector()
        self.update_button_states()
        self.on_split_mode_changed()
    
    def _on_image_list_row_changed(self, row: int):
        """Update tile preview when a different image is highlighted."""
        if 0 <= row < len(self.image_paths):
            try:
                with Image.open(self.image_paths[row]) as _img:
                    img = _img.copy()
                self.batch_tile_preview.set_image(img)
                self._update_tile_preview_grid()
                self._gen_preview_btn.setEnabled(self.selected_template is not None)
            except Exception:
                pass

    def _update_tile_preview_grid(self):
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        self.batch_tile_preview.set_grid(rows, cols)

    def _generate_gif_preview(self):
        """Generate a GIF preview for the currently highlighted image."""
        if not self.image_paths or not self.selected_template:
            return
        row = self.image_list.currentRow()
        img_path = self.image_paths[row] if 0 <= row < len(self.image_paths) else self.image_paths[0]
        try:
            from ..core.image_loader import ImageLoader, MaterialManager
            from ..core.gif_builder import GifBuilder
            from ..core.template_manager import TemplateManager

            image = ImageLoader.load_image(img_path)

            split_mode = "grid" if self.grid_mode_radio.isChecked() else "size"
            if split_mode == "grid":
                tiles = ImageLoader.split_into_tiles(
                    image, self.rows_spinbox.value(), self.cols_spinbox.value())
            else:
                tiles = ImageLoader.split_by_tile_size(
                    image, self.tile_width_spinbox.value(), self.tile_height_spinbox.value())

            if self.selected_positions:
                cols_ = (self.cols_spinbox.value() if split_mode == "grid"
                         else max(1, image.width // self.tile_width_spinbox.value()))
                filtered = []
                for r, c in self.selected_positions:
                    ti = r * cols_ + c
                    if ti < len(tiles):
                        filtered.append(tiles[ti])
                if filtered:
                    tiles = filtered

            if not tiles:
                return

            mm = MaterialManager()
            stem = Path(img_path).stem
            for i, tile in enumerate(tiles):
                mm.add_material(tile, f"{stem}_tile_{i}")

            gm, settings = TemplateManager.import_composition_template(self.selected_template)
            gb = GifBuilder()
            gb.set_output_size(self.output_width_spinbox.value(),
                               self.output_height_spinbox.value())
            gb.set_loop(0)
            if settings.get("transparent_bg"):
                gb.set_background_color(0, 0, 0, 0)
            else:
                gb.set_background_color(255, 255, 255, 255)

            root_id = gm.get_root_group_id()
            if root_id is None:
                return
            frames = gb.get_preview_frames_for_group(root_id, gm, mm)
            self.batch_preview_widget.set_frames(frames)
            self.batch_preview_widget.play()
        except Exception as e:
            QMessageBox.warning(self, "Preview Failed", f"Could not generate preview:\n{e}")

    def add_images(self):
        """Add images to the batch list"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images for Batch Processing",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_paths:
            for path in file_paths:
                if path not in self.image_paths:
                    self.image_paths.append(path)
                    item = QListWidgetItem(Path(path).name)
                    item.setToolTip(path)
                    self.image_list.addItem(item)
            
            self.update_image_count()
            self.update_button_states()
    
    def clear_images(self):
        """Clear all images from the list"""
        self.image_paths.clear()
        self.image_list.clear()
        self.update_image_count()
        self.update_button_states()
    
    def update_image_count(self):
        """Update the image count label"""
        count = len(self.image_paths)
        if count == 0:
            self.image_count_label.setText("No images selected")
        elif count == 1:
            self.image_count_label.setText("1 image selected")
        else:
            self.image_count_label.setText(f"{count} images selected")
    
    def set_templates(self, templates: Dict[str, Dict[str, Any]]):
        """
        Set available templates
        
        Args:
            templates: Dictionary of {name: template_dict}
        """
        self.template_combo.clear()
        self.template_combo.addItem("-- Select Template --", None)
        
        for name, template in templates.items():
            self.template_combo.addItem(name, template)
        
        self.update_button_states()
    
    def refresh_templates(self):
        """Signal parent to refresh templates"""
        # This will be connected in main window
        pass
    
    def on_template_selected(self, index: int):
        """Handle template selection"""
        if index <= 0:
            self.selected_template = None
            self.selected_template_name = ""
            self.template_info_label.setText("No template selected")
        else:
            self.selected_template = self.template_combo.currentData()
            self.selected_template_name = self.template_combo.currentText()

            if self.selected_template:
                from ..core.template_manager import TemplateManager
                try:
                    info = TemplateManager.get_template_info(self.selected_template)
                    self.template_info_label.setText(
                        f"Groups: {info.get('group_count', 0)} | "
                        f"Tiles needed: {info.get('materials_needed', 0)} | "
                        f"Transparent: {info.get('transparent_bg', False)} | "
                        f"Colors: {info.get('color_count', 256)}"
                    )
                except Exception as e:
                    self.template_info_label.setText(f"Template info unavailable: {e}")

        self.update_button_states()
        if hasattr(self, '_gen_preview_btn'):
            self._gen_preview_btn.setEnabled(
                self.selected_template is not None and bool(self.image_paths)
            )

    def on_split_mode_changed(self):
        """Handle split mode change"""
        is_grid = self.grid_mode_radio.isChecked()
        
        self.rows_spinbox.setEnabled(is_grid)
        self.cols_spinbox.setEnabled(is_grid)
        self.tile_width_spinbox.setEnabled(not is_grid)
        self.tile_height_spinbox.setEnabled(not is_grid)
    
    def update_position_selector(self):
        """Update the position selector grid"""
        # Clear existing buttons
        while self.position_grid_layout.count():
            child = self.position_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Create new grid
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        
        for row in range(rows):
            for col in range(cols):
                button = QPushButton(f"{row},{col}")
                button.setCheckable(True)
                button.setChecked(True)
                button.setMinimumSize(40, 40)
                button.setMaximumSize(55, 55)
                button.clicked.connect(lambda checked, r=row, c=col: self.toggle_position(r, c))
                
                self.position_grid_layout.addWidget(button, row, col)
        
        self.update_selected_positions()
    
    def toggle_position(self, row: int, col: int):
        """Toggle a position selection"""
        self.update_selected_positions()
    
    def update_selected_positions(self):
        """Update the list of selected positions"""
        self.selected_positions.clear()
        
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton) and button.isChecked():
                    text = button.text()
                    coords = text.split(',')
                    if len(coords) == 2:
                        try:
                            row = int(coords[0])
                            col = int(coords[1])
                            self.selected_positions.append((row, col))
                        except ValueError:
                            pass
    
    def select_all_positions(self):
        """Select all tile positions"""
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton):
                    button.setChecked(True)
        self.update_selected_positions()
    
    def deselect_all_positions(self):
        """Deselect all tile positions"""
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton):
                    button.setChecked(False)
        self.update_selected_positions()
    
    def on_output_mode_changed(self, checked: bool):
        """Handle output mode change"""
        self.output_dir_edit.setEnabled(not checked)
        self.browse_output_btn.setEnabled(not checked)
    
    def browse_output_directory(self):
        """Browse for output directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            ""
        )
        
        if directory:
            self.output_dir_edit.setText(directory)
    
    def validate_settings(self):
        """Validate current settings"""
        # Check images
        if not self.image_paths:
            self.show_validation_error("Please select at least one image")
            return False
        
        # Check template
        if not self.selected_template:
            self.show_validation_error("Please select a template")
            return False
        
        # Check positions
        if not self.selected_positions:
            self.show_validation_error("Please select at least one tile position")
            return False
        
        # Check output directory
        if not self.same_dir_checkbox.isChecked():
            output_dir = self.output_dir_edit.text().strip()
            if not output_dir:
                self.show_validation_error("Please select an output directory")
                return False
            
            if not Path(output_dir).exists():
                self.show_validation_error("Output directory does not exist")
                return False
        
        # Validate template compatibility
        try:
            # Use first image as sample
            sample_img = Image.open(self.image_paths[0])
            img_width, img_height = sample_img.size
            
            from ..core.batch_processor import BatchProcessor
            
            split_mode = "grid" if self.grid_mode_radio.isChecked() else "size"
            
            is_valid, message = BatchProcessor.validate_template_for_batch(
                template=self.selected_template,
                split_mode=split_mode,
                split_rows=self.rows_spinbox.value(),
                split_cols=self.cols_spinbox.value(),
                tile_width=self.tile_width_spinbox.value(),
                tile_height=self.tile_height_spinbox.value(),
                image_width=img_width,
                image_height=img_height,
                selected_positions=self.selected_positions if self.selected_positions else None
            )
            
            if is_valid:
                self.show_validation_success(message)
                return True
            else:
                self.show_validation_error(message)
                return False
                
        except Exception as e:
            self.show_validation_error(f"Validation error: {str(e)}")
            return False
    
    def show_validation_error(self, message: str):
        """Show validation error"""
        self.validation_label.setText(f"❌ {message}")
        self.validation_label.setStyleSheet(
            f"background-color: #3a1010; color: {_T.ERROR}; "
            f"padding: 5px; border-radius: 3px; border: 1px solid {_T.ERROR};"
        )
    
    def show_validation_success(self, message: str):
        """Show validation success"""
        self.validation_label.setText(f"✓ {message}")
        self.validation_label.setStyleSheet(
            f"background-color: #0d2a14; color: {_T.SUCCESS}; "
            f"padding: 5px; border-radius: 3px; border: 1px solid {_T.SUCCESS};"
        )
    
    def update_button_states(self):
        """Update button states based on current state"""
        has_images = len(self.image_paths) > 0
        has_template = self.selected_template is not None

        self.validate_btn.setEnabled(has_images and has_template)
        self.process_btn.setEnabled(has_images and has_template)
        if hasattr(self, '_gen_preview_btn'):
            self._gen_preview_btn.setEnabled(has_images and has_template)
    
    def start_batch_processing(self):
        """Start the batch processing in a background thread."""
        if not self.validate_settings():
            return

        reply = QMessageBox.question(
            self,
            "Confirm Batch Processing",
            f"Process {len(self.image_paths)} image(s) with template '{self.selected_template_name}'?\n\n"
            "Each image will be split into tiles and exported as a GIF.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting…")

        output_directory = (
            None if self.same_dir_checkbox.isChecked()
            else self.output_dir_edit.text().strip() or None
        )

        from ..core.batch_processor import BatchProcessor
        processor = BatchProcessor()

        split_mode = "grid" if self.grid_mode_radio.isChecked() else "size"
        kwargs = dict(
            image_paths=list(self.image_paths),
            template=self.selected_template,
            split_mode=split_mode,
            split_rows=self.rows_spinbox.value(),
            split_cols=self.cols_spinbox.value(),
            tile_width=self.tile_width_spinbox.value(),
            tile_height=self.tile_height_spinbox.value(),
            selected_positions=self.selected_positions if self.selected_positions else None,
            output_directory=output_directory,
            color_count=int(self.color_palette_combo.currentText()),
            output_width=self.output_width_spinbox.value(),
            output_height=self.output_height_spinbox.value(),
        )

        self._worker = _BatchWorker(processor, kwargs)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        processor.set_progress_callback(
            lambda cur, tot, msg: self._worker.progress.emit(cur, tot, msg)
        )

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.on_progress)
        self._worker.finished.connect(self._on_batch_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def on_progress(self, current: int, total: int, message: str):
        """Handle thread-safe progress updates (called via signal)."""
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.progress_label.setText(f"{message} ({current}/{total})")

    def _on_batch_finished(self, successful: list, failed: list):
        """Called when the background worker finishes."""
        self.set_ui_enabled(True)
        self.progress_bar.setValue(100 if successful else 0)
        self.progress_label.setText("Ready to process")
        self.show_results(successful, failed)
        self.batch_complete.emit(len(successful), len(failed))
    
    def show_results(self, successful: List[str], failed: List[Tuple[str, str]]):
        """Show batch processing results"""
        success_count = len(successful)
        fail_count = len(failed)
        
        message = f"Batch processing complete!\n\n"
        message += f"✓ Successfully processed: {success_count}\n"
        message += f"✗ Failed: {fail_count}\n"
        
        if failed:
            message += "\nFailed images:\n"
            for img_path, error in failed[:5]:  # Show first 5
                message += f"• {Path(img_path).name}: {error}\n"
            
            if len(failed) > 5:
                message += f"... and {len(failed) - 5} more"
        
        if success_count > 0:
            QMessageBox.information(self, "Batch Processing Complete", message)
        else:
            QMessageBox.warning(self, "Batch Processing Complete", message)
    
    def set_ui_enabled(self, enabled: bool):
        """Enable or disable UI elements during processing"""
        self.add_images_btn.setEnabled(enabled)
        self.clear_images_btn.setEnabled(enabled)
        self.template_combo.setEnabled(enabled)
        self.refresh_templates_btn.setEnabled(enabled)
        self.grid_mode_radio.setEnabled(enabled)
        self.size_mode_radio.setEnabled(enabled)
        self.rows_spinbox.setEnabled(enabled)
        self.cols_spinbox.setEnabled(enabled)
        self.tile_width_spinbox.setEnabled(enabled)
        self.tile_height_spinbox.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
        self.output_width_spinbox.setEnabled(enabled)
        self.output_height_spinbox.setEnabled(enabled)
        self.color_palette_combo.setEnabled(enabled)
        self.same_dir_checkbox.setEnabled(enabled)
        self.browse_output_btn.setEnabled(enabled and not self.same_dir_checkbox.isChecked())
        self.validate_btn.setEnabled(enabled)
        self.process_btn.setEnabled(enabled)
        
        # Disable position buttons
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(enabled)

