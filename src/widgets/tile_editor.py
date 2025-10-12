from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
                              QGridLayout, QFrame)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from pathlib import Path
from typing import List, Tuple


class TileEditorWidget(QWidget):
    
    tiles_created = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_images: List[Image.Image] = []
        self.current_image_paths: List[str] = []
        self.selected_positions: List[Tuple[int, int]] = []  # (row, col)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("Tile Splitter")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Load images section
        load_group = QGroupBox("Load Images")
        load_layout = QVBoxLayout()
        
        self.load_single_button = QPushButton("Load Single Image")
        self.load_single_button.clicked.connect(self.load_single_image)
        load_layout.addWidget(self.load_single_button)
        
        self.load_multiple_button = QPushButton("Load Multiple Images")
        self.load_multiple_button.clicked.connect(self.load_multiple_images)
        load_layout.addWidget(self.load_multiple_button)
        
        self.clear_images_button = QPushButton("Clear All Images")
        self.clear_images_button.clicked.connect(self.clear_images)
        load_layout.addWidget(self.clear_images_button)
        
        self.image_info_label = QLabel("No images loaded")
        load_layout.addWidget(self.image_info_label)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        # Split settings section
        settings_group = QGroupBox("Split Settings")
        settings_layout = QVBoxLayout()
        
        grid_group = QGroupBox("Split by Grid Count")
        grid_layout = QVBoxLayout()
        
        rows_layout = QHBoxLayout()
        rows_layout.addWidget(QLabel("Rows:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setMinimum(1)
        self.rows_spinbox.setMaximum(100)
        self.rows_spinbox.setValue(4)
        self.rows_spinbox.valueChanged.connect(self.update_position_selector)
        rows_layout.addWidget(self.rows_spinbox)
        grid_layout.addLayout(rows_layout)
        
        cols_layout = QHBoxLayout()
        cols_layout.addWidget(QLabel("Columns:"))
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setMinimum(1)
        self.cols_spinbox.setMaximum(100)
        self.cols_spinbox.setValue(4)
        self.cols_spinbox.valueChanged.connect(self.update_position_selector)
        cols_layout.addWidget(self.cols_spinbox)
        grid_layout.addLayout(cols_layout)
        
        self.split_by_grid_button = QPushButton("Split by Grid")
        self.split_by_grid_button.clicked.connect(self.split_by_grid)
        grid_layout.addWidget(self.split_by_grid_button)
        
        grid_group.setLayout(grid_layout)
        settings_layout.addWidget(grid_group)
        
        size_group = QGroupBox("Split by Tile Size")
        size_layout = QVBoxLayout()
        
        tile_width_layout = QHBoxLayout()
        tile_width_layout.addWidget(QLabel("Tile Width:"))
        self.tile_width_spinbox = QSpinBox()
        self.tile_width_spinbox.setMinimum(1)
        self.tile_width_spinbox.setMaximum(10000)
        self.tile_width_spinbox.setValue(32)
        tile_width_layout.addWidget(self.tile_width_spinbox)
        size_layout.addLayout(tile_width_layout)
        
        tile_height_layout = QHBoxLayout()
        tile_height_layout.addWidget(QLabel("Tile Height:"))
        self.tile_height_spinbox = QSpinBox()
        self.tile_height_spinbox.setMinimum(1)
        self.tile_height_spinbox.setMaximum(10000)
        self.tile_height_spinbox.setValue(32)
        tile_height_layout.addWidget(self.tile_height_spinbox)
        size_layout.addLayout(tile_height_layout)
        
        self.split_by_size_button = QPushButton("Split by Size")
        self.split_by_size_button.clicked.connect(self.split_by_size)
        size_layout.addWidget(self.split_by_size_button)
        
        size_group.setLayout(size_layout)
        settings_layout.addWidget(size_group)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Position selector section
        self.position_group = QGroupBox("Select Positions to Keep")
        position_layout = QVBoxLayout()
        
        position_controls = QHBoxLayout()
        
        self.select_all_positions_button = QPushButton("Select All")
        self.select_all_positions_button.clicked.connect(self.select_all_positions)
        position_controls.addWidget(self.select_all_positions_button)
        
        self.deselect_all_positions_button = QPushButton("Deselect All")
        self.deselect_all_positions_button.clicked.connect(self.deselect_all_positions)
        position_controls.addWidget(self.deselect_all_positions_button)
        
        position_layout.addLayout(position_controls)
        
        # Position grid
        self.position_grid_widget = QWidget()
        self.position_grid_layout = QGridLayout()
        self.position_grid_widget.setLayout(self.position_grid_layout)
        position_layout.addWidget(self.position_grid_widget)
        
        self.position_group.setLayout(position_layout)
        layout.addWidget(self.position_group)
        
        self.result_label = QLabel("")
        layout.addWidget(self.result_label)
        
        layout.addStretch()
        
        self.setLayout(layout)
        
        self.update_button_states()
        self.update_position_selector()
    
    def load_single_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image to Split",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            self.load_image_from_path(file_path)
    
    def load_multiple_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images to Split",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_paths:
            for file_path in file_paths:
                self.load_image_from_path(file_path)
    
    def load_image_from_path(self, file_path: str):
        try:
            image = Image.open(file_path)
            self.current_images.append(image)
            self.current_image_paths.append(file_path)
            
            self.update_image_info()
            self.update_button_states()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image {Path(file_path).name}:\n{str(e)}")
    
    def clear_images(self):
        self.current_images.clear()
        self.current_image_paths.clear()
        self.selected_positions.clear()
        
        self.update_image_info()
        self.update_button_states()
    
    def update_image_info(self):
        if not self.current_images:
            self.image_info_label.setText("No images loaded")
        elif len(self.current_images) == 1:
            width, height = self.current_images[0].size
            self.image_info_label.setText(
                f"Image: {Path(self.current_image_paths[0]).name}\n"
                f"Size: {width} x {height} pixels"
            )
        else:
            self.image_info_label.setText(f"Loaded {len(self.current_images)} images")
    
    def update_position_selector(self):
        # Clear existing position buttons
        while self.position_grid_layout.count():
            child = self.position_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Create new position selector grid
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        
        for row in range(rows):
            for col in range(cols):
                button = QPushButton(f"({row},{col})")
                button.setCheckable(True)
                button.setChecked(True)  # Default to selected
                button.setMinimumSize(40, 40)
                button.clicked.connect(lambda checked, r=row, c=col: self.toggle_position(r, c))
                
                self.position_grid_layout.addWidget(button, row, col)
        
        # Update selected positions
        self.update_selected_positions()
    
    def toggle_position(self, row: int, col: int):
        self.update_selected_positions()
    
    def update_selected_positions(self):
        self.selected_positions.clear()
        
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton) and button.isChecked():
                    # Extract position from button text
                    text = button.text()
                    if text.startswith('(') and text.endswith(')'):
                        coords = text[1:-1].split(',')
                        if len(coords) == 2:
                            try:
                                row = int(coords[0])
                                col = int(coords[1])
                                self.selected_positions.append((row, col))
                            except ValueError:
                                pass
    
    def select_all_positions(self):
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton):
                    button.setChecked(True)
        self.update_selected_positions()
    
    def deselect_all_positions(self):
        for i in range(self.position_grid_layout.count()):
            item = self.position_grid_layout.itemAt(i)
            if item and item.widget():
                button = item.widget()
                if isinstance(button, QPushButton):
                    button.setChecked(False)
        self.update_selected_positions()
    
    def split_by_grid(self):
        if not self.current_images:
            QMessageBox.warning(self, "Warning", "Please load at least one image first!")
            return
        
        if not self.selected_positions:
            QMessageBox.warning(self, "Warning", "Please select at least one position to keep!")
            return
        
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            selected_tiles = []
            
            for img_idx, image in enumerate(self.current_images):
                tiles = ImageLoader.split_into_tiles(image, rows, cols)
                
                for row, col in self.selected_positions:
                    tile_idx = row * cols + col
                    if tile_idx < len(tiles):
                        selected_tiles.append(tiles[tile_idx])
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles from {len(self.current_images)} images")
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(selected_tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Successfully created {len(selected_tiles)} tiles!\n"
                f"Selected positions: {len(self.selected_positions)}\n"
                f"Images processed: {len(self.current_images)}\n"
                f"The tiles have been added to your materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split images:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def split_by_size(self):
        if not self.current_images:
            QMessageBox.warning(self, "Warning", "Please load at least one image first!")
            return
        
        if not self.selected_positions:
            QMessageBox.warning(self, "Warning", "Please select at least one position to keep!")
            return
        
        tile_width = self.tile_width_spinbox.value()
        tile_height = self.tile_height_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            selected_tiles = []
            
            for img_idx, image in enumerate(self.current_images):
                tiles = ImageLoader.split_by_tile_size(image, tile_width, tile_height)
                
                img_width, img_height = image.size
                cols = img_width // tile_width
                rows = img_height // tile_height
                
                for row, col in self.selected_positions:
                    tile_idx = row * cols + col
                    if tile_idx < len(tiles):
                        selected_tiles.append(tiles[tile_idx])
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles from {len(self.current_images)} images")
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(selected_tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Successfully created {len(selected_tiles)} tiles!\n"
                f"Selected positions: {len(self.selected_positions)}\n"
                f"Images processed: {len(self.current_images)}\n"
                f"Tile size: {tile_width}x{tile_height} pixels\n"
                f"The tiles have been added to your materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split images:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def update_button_states(self):
        has_images = len(self.current_images) > 0
        self.split_by_grid_button.setEnabled(has_images)
        self.split_by_size_button.setEnabled(has_images)
        self.clear_images_button.setEnabled(has_images)