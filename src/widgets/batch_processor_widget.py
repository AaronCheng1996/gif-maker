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
                              QCheckBox, QLineEdit)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional


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
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Automatically split images into tiles and generate GIFs using a template.\n"
            "Each image will be processed: split → apply template → export as GIF."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 11px;")
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
        self.image_count_label.setStyleSheet("color: #666;")
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
        self.template_info_label.setStyleSheet("color: #666; font-size: 10px;")
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
        position_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
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
        self.validation_label.setStyleSheet("padding: 5px; border-radius: 3px;")
        layout.addWidget(self.validation_label)
        
        # === Progress Section ===
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Ready to process")
        self.progress_label.setStyleSheet("color: #666;")
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
        self.process_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        action_layout.addWidget(self.process_btn)
        
        layout.addLayout(action_layout)
        
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Initialize
        self.update_position_selector()
        self.update_button_states()
        self.on_split_mode_changed()
    
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
                info = TemplateManager.get_template_info(self.selected_template)
                # Determine materials needed depending on format
                fmt = info.get('format')
                materials_needed = None
                if fmt == 'multi_timeline' or ("timelines" in self.selected_template and "timebase" in self.selected_template):
                    # For multi-timeline, require at least max material index + 1 (0-based)
                    max_index = -1
                    for tl in self.selected_template.get('timelines', []):
                        for fr in tl.get('frames', []):
                            if isinstance(fr, dict):
                                mi = fr.get('material_index')
                                if isinstance(mi, int) and mi > max_index:
                                    max_index = mi
                    materials_needed = max_index + 1 if max_index >= 0 else 0
                else:
                    materials_needed = info.get('material_count', 0)
                
                self.template_info_label.setText(
                    f"Frames: {info.get('frame_count', 0)} | "
                    f"Materials needed: {materials_needed} | "
                    f"Size: {info.get('output_size', (0, 0))[0]}×{info.get('output_size', (0, 0))[1]} | "
                    f"Loop: {info.get('loop_count', 0)}"
                )
        
        self.update_button_states()
    
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
            "background-color: #ffebee; color: #c62828; "
            "padding: 5px; border-radius: 3px; border: 1px solid #ef5350;"
        )
    
    def show_validation_success(self, message: str):
        """Show validation success"""
        self.validation_label.setText(f"✓ {message}")
        self.validation_label.setStyleSheet(
            "background-color: #e8f5e9; color: #2e7d32; "
            "padding: 5px; border-radius: 3px; border: 1px solid #66bb6a;"
        )
    
    def update_button_states(self):
        """Update button states based on current state"""
        has_images = len(self.image_paths) > 0
        has_template = self.selected_template is not None
        
        self.validate_btn.setEnabled(has_images and has_template)
        self.process_btn.setEnabled(has_images and has_template)
    
    def start_batch_processing(self):
        """Start the batch processing"""
        # Validate first
        if not self.validate_settings():
            return
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Batch Processing",
            f"Process {len(self.image_paths)} image(s) with template '{self.selected_template_name}'?\n\n"
            f"Each image will be split into tiles and exported as a GIF.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Disable UI during processing
        self.set_ui_enabled(False)
        
        # Get output directory
        if self.same_dir_checkbox.isChecked():
            output_directory = None
        else:
            output_directory = self.output_dir_edit.text().strip()
        
        # Process batch
        try:
            from ..core.batch_processor import BatchProcessor
            
            processor = BatchProcessor()
            processor.set_progress_callback(self.on_progress)
            
            split_mode = "grid" if self.grid_mode_radio.isChecked() else "size"
            
            # Get color count from UI
            color_count = int(self.color_palette_combo.currentText())
            
            successful, failed = processor.process_batch(
                image_paths=self.image_paths,
                template=self.selected_template,
                split_mode=split_mode,
                split_rows=self.rows_spinbox.value(),
                split_cols=self.cols_spinbox.value(),
                tile_width=self.tile_width_spinbox.value(),
                tile_height=self.tile_height_spinbox.value(),
                selected_positions=self.selected_positions if self.selected_positions else None,
                output_directory=output_directory,
                color_count=color_count
            )
            
            # Show results
            self.show_results(successful, failed)
            
            # Emit completion signal
            self.batch_complete.emit(len(successful), len(failed))
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Batch Processing Error",
                f"An error occurred during batch processing:\n{str(e)}"
            )
        finally:
            # Re-enable UI
            self.set_ui_enabled(True)
            self.progress_bar.setValue(0)
            self.progress_label.setText("Ready to process")
    
    def on_progress(self, current: int, total: int, message: str):
        """Handle progress updates"""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
        
        self.progress_label.setText(f"{message} ({current}/{total})")
        
        # Process events to update UI
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
    
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
        self.same_dir_checkbox.setEnabled(enabled)
        self.browse_output_btn.setEnabled(enabled and not self.same_dir_checkbox.isChecked())
        self.validate_btn.setEnabled(enabled)
        self.process_btn.setEnabled(enabled)
        
        # Disable position buttons
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(enabled)

