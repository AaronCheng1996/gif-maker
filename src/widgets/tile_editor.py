from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
                              QGridLayout, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                              QCheckBox, QScrollArea)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from pathlib import Path
from typing import List, Tuple


class TileEditorWidget(QWidget):
    
    tiles_created = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.loaded_images: List[Tuple[Image.Image, str]] = []  # (image, path)
        self.selected_positions: List[Tuple[int, int]] = []  # (row, col)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        title_label = QLabel("Tile Splitter")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Load images section (compact)
        load_layout = QHBoxLayout()
        
        self.load_single_button = QPushButton("Load Image")
        self.load_single_button.clicked.connect(self.load_single_image)
        self.load_single_button.setMaximumHeight(25)
        load_layout.addWidget(self.load_single_button)
        
        self.load_multiple_button = QPushButton("Load Multiple")
        self.load_multiple_button.clicked.connect(self.load_multiple_images)
        self.load_multiple_button.setMaximumHeight(25)
        load_layout.addWidget(self.load_multiple_button)
        
        self.clear_images_button = QPushButton("Clear")
        self.clear_images_button.clicked.connect(self.clear_images)
        self.clear_images_button.setMaximumHeight(25)
        load_layout.addWidget(self.clear_images_button)
        
        layout.addLayout(load_layout)
        
        # Loaded images preview table
        self.images_table = QTableWidget()
        self.images_table.setColumnCount(3)
        self.images_table.setHorizontalHeaderLabels(["Preview", "Filename", "Size"])
        self.images_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.images_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.images_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.images_table.setColumnWidth(0, 60)
        self.images_table.setColumnWidth(2, 80)
        self.images_table.setIconSize(QSize(48, 48))
        self.images_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.images_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.images_table.verticalHeader().setVisible(False)
        layout.addWidget(self.images_table, stretch=1)  # Give it stretch to take remaining space
        
        # Split settings section (compact)
        settings_group = QGroupBox("Split Settings")
        settings_layout = QHBoxLayout()
        
        # Grid settings
        settings_layout.addWidget(QLabel("Grid:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setMinimum(1)
        self.rows_spinbox.setMaximum(100)
        self.rows_spinbox.setValue(4)
        self.rows_spinbox.setMaximumWidth(50)
        self.rows_spinbox.valueChanged.connect(self.update_position_selector)
        settings_layout.addWidget(self.rows_spinbox)
        
        settings_layout.addWidget(QLabel("×"))
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setMinimum(1)
        self.cols_spinbox.setMaximum(100)
        self.cols_spinbox.setValue(4)
        self.cols_spinbox.setMaximumWidth(50)
        self.cols_spinbox.valueChanged.connect(self.update_position_selector)
        settings_layout.addWidget(self.cols_spinbox)
        
        self.split_by_grid_button = QPushButton("Split by Grid")
        self.split_by_grid_button.clicked.connect(self.split_by_grid)
        self.split_by_grid_button.setMaximumHeight(25)
        settings_layout.addWidget(self.split_by_grid_button)
        
        settings_layout.addWidget(QLabel("|"))
        
        # Size settings
        settings_layout.addWidget(QLabel("Size:"))
        self.tile_width_spinbox = QSpinBox()
        self.tile_width_spinbox.setMinimum(1)
        self.tile_width_spinbox.setMaximum(10000)
        self.tile_width_spinbox.setValue(32)
        self.tile_width_spinbox.setMaximumWidth(50)
        settings_layout.addWidget(self.tile_width_spinbox)
        
        settings_layout.addWidget(QLabel("×"))
        self.tile_height_spinbox = QSpinBox()
        self.tile_height_spinbox.setMinimum(1)
        self.tile_height_spinbox.setMaximum(10000)
        self.tile_height_spinbox.setValue(32)
        self.tile_height_spinbox.setMaximumWidth(50)
        settings_layout.addWidget(self.tile_height_spinbox)
        
        self.split_by_size_button = QPushButton("Split by Size")
        self.split_by_size_button.clicked.connect(self.split_by_size)
        self.split_by_size_button.setMaximumHeight(25)
        settings_layout.addWidget(self.split_by_size_button)
        
        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Position selector section
        self.position_group = QGroupBox("Select Tile Positions to Keep")
        position_layout = QVBoxLayout()
        position_layout.setSpacing(3)
        
        position_controls = QHBoxLayout()
        
        self.select_all_positions_button = QPushButton("Select All")
        self.select_all_positions_button.clicked.connect(self.select_all_positions)
        self.select_all_positions_button.setMaximumHeight(25)
        position_controls.addWidget(self.select_all_positions_button)
        
        self.deselect_all_positions_button = QPushButton("Deselect All")
        self.deselect_all_positions_button.clicked.connect(self.deselect_all_positions)
        self.deselect_all_positions_button.setMaximumHeight(25)
        position_controls.addWidget(self.deselect_all_positions_button)
        
        position_layout.addLayout(position_controls)
        
        # Position grid (scrollable)
        position_scroll = QScrollArea()
        position_scroll.setWidgetResizable(True)
        position_scroll.setMaximumHeight(200)
        
        self.position_grid_widget = QWidget()
        self.position_grid_layout = QGridLayout()
        self.position_grid_widget.setLayout(self.position_grid_layout)
        position_scroll.setWidget(self.position_grid_widget)
        
        position_layout.addWidget(position_scroll)
        
        self.position_group.setLayout(position_layout)
        layout.addWidget(self.position_group)
        
        self.result_label = QLabel("")
        layout.addWidget(self.result_label)
        
        layout.addStretch()
        
        self.setLayout(layout)
        
        self.update_button_states()
        self.update_position_selector()
    
    def create_thumbnail(self, pil_image: Image.Image, width: int, height: int) -> QPixmap:
        """Create a thumbnail from PIL image"""
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
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
            self.loaded_images.append((image, file_path))
            
            self.update_images_table()
            self.update_button_states()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image {Path(file_path).name}:\n{str(e)}")
    
    def update_images_table(self):
        """Update the loaded images table"""
        self.images_table.setRowCount(0)
        
        for i, (img, path) in enumerate(self.loaded_images):
            self.images_table.insertRow(i)
            
            # Preview
            preview_item = QTableWidgetItem()
            thumbnail = self.create_thumbnail(img, 48, 48)
            preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 0, preview_item)
            
            # Filename
            filename = Path(path).name
            filename_item = QTableWidgetItem(filename)
            filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 1, filename_item)
            
            # Size
            size_text = f"{img.width}×{img.height}"
            size_item = QTableWidgetItem(size_text)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 2, size_item)
            
            self.images_table.setRowHeight(i, 54)
    
    def clear_images(self):
        self.loaded_images.clear()
        self.selected_positions.clear()
        
        self.update_images_table()
        self.update_button_states()
    
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
                button = QPushButton(f"{row},{col}")
                button.setCheckable(True)
                button.setChecked(True)  # Default to selected
                button.setMinimumSize(35, 35)
                button.setMaximumSize(50, 50)
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
                    coords = text.split(',')
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
        # Get selected images
        selected_rows = sorted(set(item.row() for item in self.images_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one image from the table!")
            return
        
        if not self.selected_positions:
            QMessageBox.warning(self, "Warning", "Please select at least one position to keep!")
            return
        
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            selected_tiles = []
            
            for img_idx in selected_rows:
                if img_idx < len(self.loaded_images):
                    img, path = self.loaded_images[img_idx]
                    tiles = ImageLoader.split_into_tiles(img, rows, cols)
                    
                    for row, col in self.selected_positions:
                        tile_idx = row * cols + col
                        if tile_idx < len(tiles):
                            selected_tiles.append(tiles[tile_idx])
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles")
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(selected_tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Created {len(selected_tiles)} tiles!\n"
                f"Images: {len(selected_rows)}\n"
                f"Positions: {len(self.selected_positions)}\n"
                f"Tiles added to materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split images:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def split_by_size(self):
        # Get selected images
        selected_rows = sorted(set(item.row() for item in self.images_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one image from the table!")
            return
        
        if not self.selected_positions:
            QMessageBox.warning(self, "Warning", "Please select at least one position to keep!")
            return
        
        tile_width = self.tile_width_spinbox.value()
        tile_height = self.tile_height_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            selected_tiles = []
            
            for img_idx in selected_rows:
                if img_idx < len(self.loaded_images):
                    img, path = self.loaded_images[img_idx]
                    tiles = ImageLoader.split_by_tile_size(img, tile_width, tile_height)
                    
                    img_width, img_height = img.size
                    cols = img_width // tile_width
                    rows = img_height // tile_height
                    
                    for row, col in self.selected_positions:
                        tile_idx = row * cols + col
                        if tile_idx < len(tiles):
                            selected_tiles.append(tiles[tile_idx])
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles")
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(selected_tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Created {len(selected_tiles)} tiles!\n"
                f"Images: {len(selected_rows)}\n"
                f"Positions: {len(self.selected_positions)}\n"
                f"Tile size: {tile_width}×{tile_height}\n"
                f"Tiles added to materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split images:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def update_button_states(self):
        has_images = len(self.loaded_images) > 0
        self.split_by_grid_button.setEnabled(has_images)
        self.split_by_size_button.setEnabled(has_images)
        self.clear_images_button.setEnabled(has_images)
