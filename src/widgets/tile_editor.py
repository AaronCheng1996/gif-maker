from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QSpinBox, QGroupBox, QFileDialog, QMessageBox)
from PyQt6.QtCore import pyqtSignal
from PIL import Image
from pathlib import Path


class TileEditorWidget(QWidget):
    
    tiles_created = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_image: Image.Image = None
        self.current_image_path: str = ""
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("Tile Splitter")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        self.load_image_button = QPushButton("Load Image for Splitting")
        self.load_image_button.clicked.connect(self.load_image)
        layout.addWidget(self.load_image_button)
        
        self.image_info_label = QLabel("No image loaded")
        layout.addWidget(self.image_info_label)
        
        grid_group = QGroupBox("Split by Grid Count")
        grid_layout = QVBoxLayout()
        
        rows_layout = QHBoxLayout()
        rows_layout.addWidget(QLabel("Rows:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setMinimum(1)
        self.rows_spinbox.setMaximum(100)
        self.rows_spinbox.setValue(4)
        rows_layout.addWidget(self.rows_spinbox)
        grid_layout.addLayout(rows_layout)
        
        cols_layout = QHBoxLayout()
        cols_layout.addWidget(QLabel("Columns:"))
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setMinimum(1)
        self.cols_spinbox.setMaximum(100)
        self.cols_spinbox.setValue(4)
        cols_layout.addWidget(self.cols_spinbox)
        grid_layout.addLayout(cols_layout)
        
        self.split_by_grid_button = QPushButton("Split by Grid")
        self.split_by_grid_button.clicked.connect(self.split_by_grid)
        grid_layout.addWidget(self.split_by_grid_button)
        
        grid_group.setLayout(grid_layout)
        layout.addWidget(grid_group)
        
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
        layout.addWidget(size_group)
        
        self.result_label = QLabel("")
        layout.addWidget(self.result_label)
        
        layout.addStretch()
        
        self.setLayout(layout)
        
        self.update_button_states()
    
    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image to Split",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                self.current_image = Image.open(file_path)
                self.current_image_path = file_path
                
                width, height = self.current_image.size
                self.image_info_label.setText(
                    f"Image: {Path(file_path).name}\n"
                    f"Size: {width} x {height} pixels"
                )
                
                self.tile_width_spinbox.setValue(width // 4)
                self.tile_height_spinbox.setValue(height // 4)
                
                self.update_button_states()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
    
    def split_by_grid(self):
        if not self.current_image:
            QMessageBox.warning(self, "Warning", "Please load an image first!")
            return
        
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            tiles = ImageLoader.split_into_tiles(self.current_image, rows, cols)
            
            self.result_label.setText(f"✓ Created {len(tiles)} tiles ({rows}x{cols})")
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Successfully split image into {len(tiles)} tiles!\n"
                f"The tiles have been added to your materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split image:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def split_by_size(self):
        if not self.current_image:
            QMessageBox.warning(self, "Warning", "Please load an image first!")
            return
        
        tile_width = self.tile_width_spinbox.value()
        tile_height = self.tile_height_spinbox.value()
        
        try:
            from ..core.image_loader import ImageLoader
            
            tiles = ImageLoader.split_by_tile_size(self.current_image, tile_width, tile_height)
            
            img_width, img_height = self.current_image.size
            cols = img_width // tile_width
            rows = img_height // tile_height
            
            self.result_label.setText(
                f"✓ Created {len(tiles)} tiles "
                f"({tile_width}x{tile_height} px, {rows}x{cols} grid)"
            )
            self.result_label.setStyleSheet("color: green;")
            
            self.tiles_created.emit(tiles)
            
            QMessageBox.information(
                self,
                "Success",
                f"Successfully split image into {len(tiles)} tiles!\n"
                f"Tile size: {tile_width}x{tile_height} pixels\n"
                f"Grid: {rows}x{cols}\n"
                f"The tiles have been added to your materials."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to split image:\n{str(e)}")
            self.result_label.setText(f"✗ Error: {str(e)}")
            self.result_label.setStyleSheet("color: red;")
    
    def update_button_states(self):
        has_image = self.current_image is not None
        self.split_by_grid_button.setEnabled(has_image)
        self.split_by_size_button.setEnabled(has_image)

