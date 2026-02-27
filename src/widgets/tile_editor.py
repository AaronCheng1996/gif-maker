from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
                              QGridLayout, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                              QCheckBox, QScrollArea, QSplitter)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QRectF
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QPen, QColor
from PIL import Image
from pathlib import Path
from typing import List, Tuple, Optional, Set

from .theme import AppTheme as _T


class TileEditorWidget(QWidget):
    
    tiles_created = pyqtSignal(list)  # List[Tuple[Image, str]] - (tile_image, source_filename)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.loaded_images: List[Tuple[Image.Image, str]] = []  # (image, path)
        self.selected_positions: List[Tuple[int, int]] = []  # (row, col)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        title_label = QLabel("Tile Splitter")
        title_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
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
        
        # Split settings section (compact, multi-row)
        settings_group = QGroupBox("Split Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(5)
        
        # Grid settings row
        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("Grid:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setMinimum(1)
        self.rows_spinbox.setMaximum(100)
        self.rows_spinbox.setValue(4)
        self.rows_spinbox.setMaximumWidth(50)
        self.rows_spinbox.valueChanged.connect(self.update_position_selector)
        grid_layout.addWidget(self.rows_spinbox)
        
        grid_layout.addWidget(QLabel("×"))
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setMinimum(1)
        self.cols_spinbox.setMaximum(100)
        self.cols_spinbox.setValue(4)
        self.cols_spinbox.setMaximumWidth(50)
        self.cols_spinbox.valueChanged.connect(self.update_position_selector)
        grid_layout.addWidget(self.cols_spinbox)
        
        self.split_by_grid_button = QPushButton("Split by Grid")
        self.split_by_grid_button.clicked.connect(self.split_by_grid)
        self.split_by_grid_button.setMaximumHeight(25)
        grid_layout.addWidget(self.split_by_grid_button)
        grid_layout.addStretch()

        self.row_base_checkbox = QCheckBox("Row Base")
        self.row_base_checkbox.setChecked(True)
        grid_layout.addWidget(self.row_base_checkbox)
        
        settings_layout.addLayout(grid_layout)
        
        # Size settings row
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        self.tile_width_spinbox = QSpinBox()
        self.tile_width_spinbox.setMinimum(1)
        self.tile_width_spinbox.setMaximum(10000)
        self.tile_width_spinbox.setValue(32)
        self.tile_width_spinbox.setMaximumWidth(50)
        size_layout.addWidget(self.tile_width_spinbox)
        
        size_layout.addWidget(QLabel("×"))
        self.tile_height_spinbox = QSpinBox()
        self.tile_height_spinbox.setMinimum(1)
        self.tile_height_spinbox.setMaximum(10000)
        self.tile_height_spinbox.setValue(32)
        self.tile_height_spinbox.setMaximumWidth(50)
        size_layout.addWidget(self.tile_height_spinbox)
        
        self.split_by_size_button = QPushButton("Split by Size")
        self.split_by_size_button.clicked.connect(self.split_by_size)
        self.split_by_size_button.setMaximumHeight(25)
        size_layout.addWidget(self.split_by_size_button)
        size_layout.addStretch()
        
        settings_layout.addLayout(size_layout)
        
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
        selected_rows = sorted({item.row() for item in self.images_table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one image from the table!")
            return
        
        if not self.selected_positions:
            QMessageBox.warning(self, "Warning", "Please select at least one position to keep!")
            return
        
        rows = self.rows_spinbox.value()
        cols = self.cols_spinbox.value()
        row_base = self.row_base_checkbox.isChecked()
        
        try:
            from ..core.image_loader import ImageLoader
            
            selected_tiles = []  # List[Tuple[Image, str]]
            
            for img_idx in selected_rows:
                if img_idx < len(self.loaded_images):
                    img, img_path = self.loaded_images[img_idx]
                    source_filename = Path(img_path).stem  # Get filename without extension
                    tiles = ImageLoader.split_into_tiles(img, rows, cols, row_base=row_base)
                    
                    for row, col in self.selected_positions:
                        tile_idx = row * cols + col
                        if tile_idx < len(tiles):
                            # Attach source filename to each tile
                            selected_tiles.append((tiles[tile_idx], source_filename))
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles")
            self.result_label.setStyleSheet(f"color: {_T.SUCCESS};")
            
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
            self.result_label.setStyleSheet(f"color: {_T.ERROR};")
    
    def split_by_size(self):
        # Get selected images
        selected_rows = sorted({item.row() for item in self.images_table.selectedIndexes()})
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
            
            selected_tiles = []  # List[Tuple[Image, str]]
            
            for img_idx in selected_rows:
                if img_idx < len(self.loaded_images):
                    img, img_path = self.loaded_images[img_idx]
                    source_filename = Path(img_path).stem  # Get filename without extension
                    tiles = ImageLoader.split_by_tile_size(img, tile_width, tile_height)
                    
                    img_width, img_height = img.size
                    cols = img_width // tile_width
                    
                    for row, col in self.selected_positions:
                        tile_idx = row * cols + col
                        if tile_idx < len(tiles):
                            # Attach source filename to each tile
                            selected_tiles.append((tiles[tile_idx], source_filename))
            
            if not selected_tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles found for selected positions!")
                return
            
            self.result_label.setText(f"✓ Created {len(selected_tiles)} tiles")
            self.result_label.setStyleSheet(f"color: {_T.SUCCESS};")
            
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
            self.result_label.setStyleSheet(f"color: {_T.ERROR};")
    
    def update_button_states(self):
        has_images = len(self.loaded_images) > 0
        self.split_by_grid_button.setEnabled(has_images)
        self.split_by_size_button.setEnabled(has_images)
        self.clear_images_button.setEnabled(has_images)


# ──────────────────────────────────────────────────────────────────────────────
# TilePreviewWidget — interactive image canvas with grid overlay & cell toggle
# ──────────────────────────────────────────────────────────────────────────────

class TilePreviewWidget(QWidget):
    """Displays an image with a tile-grid overlay. Click cells to toggle selection."""

    selection_changed = pyqtSignal(list)  # List[Tuple[int, int]] selected (row, col)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pil_image: Optional[Image.Image] = None
        self._rows = 4
        self._cols = 4
        self._selected: Set[Tuple[int, int]] = set()
        # Cached geometry of the scaled image (updated in paintEvent)
        self._img_x = 0
        self._img_y = 0
        self._img_w = 0
        self._img_h = 0
        self.setMinimumSize(200, 200)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── public API ──────────────────────────────────────────────

    def set_image(self, pil_image: Optional[Image.Image]):
        self._pil_image = pil_image
        self._select_all()
        self.update()

    def set_grid(self, rows: int, cols: int):
        self._rows = max(1, rows)
        self._cols = max(1, cols)
        self._select_all()
        self.update()

    def select_all(self):
        self._select_all()
        self.update()

    def deselect_all(self):
        self._selected = set()
        self.selection_changed.emit([])
        self.update()

    def get_selected_positions(self) -> List[Tuple[int, int]]:
        return sorted(self._selected)

    # ── internal ────────────────────────────────────────────────

    def _select_all(self):
        self._selected = {(r, c) for r in range(self._rows) for c in range(self._cols)}
        self.selection_changed.emit(list(self._selected))

    def _cell_rect(self, row: int, col: int) -> QRectF:
        if self._img_w == 0 or self._img_h == 0:
            return QRectF()
        cw = self._img_w / self._cols
        ch = self._img_h / self._rows
        return QRectF(self._img_x + col * cw, self._img_y + row * ch, cw, ch)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(_T.BG))

        if self._pil_image is None:
            painter.setPen(QColor(_T.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Select an image on the left to preview")
            return

        # Convert PIL → QPixmap and scale to fit
        img = self._pil_image.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)

        w, h = self.width() - 4, self.height() - 4
        scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self._img_x = (self.width() - scaled.width()) // 2
        self._img_y = (self.height() - scaled.height()) // 2
        self._img_w = scaled.width()
        self._img_h = scaled.height()
        painter.drawPixmap(self._img_x, self._img_y, scaled)

        # Draw grid cells
        cw = self._img_w / self._cols
        ch = self._img_h / self._rows
        for r in range(self._rows):
            for c in range(self._cols):
                rect = QRectF(self._img_x + c * cw, self._img_y + r * ch, cw, ch)
                if (r, c) in self._selected:
                    painter.fillRect(rect, QColor(80, 200, 100, 70))
                    painter.setPen(QPen(QColor(80, 220, 100), 1.5))
                else:
                    painter.fillRect(rect, QColor(200, 60, 60, 50))
                    painter.setPen(QPen(QColor(220, 80, 80, 180), 1))
                painter.drawRect(rect)

        # Count label
        n = len(self._selected)
        total = self._rows * self._cols
        painter.setPen(QColor(_T.TEXT))
        painter.drawText(4, self.height() - 6, f"{n}/{total} tiles selected")

    def mousePressEvent(self, event):
        if self._pil_image is None or self._img_w == 0:
            return
        mx, my = event.position().x(), event.position().y()
        if not (self._img_x <= mx < self._img_x + self._img_w and
                self._img_y <= my < self._img_y + self._img_h):
            return
        cw = self._img_w / self._cols
        ch = self._img_h / self._rows
        col = int((mx - self._img_x) / cw)
        row = int((my - self._img_y) / ch)
        if 0 <= row < self._rows and 0 <= col < self._cols:
            if (row, col) in self._selected:
                self._selected.discard((row, col))
            else:
                self._selected.add((row, col))
            self.selection_changed.emit(list(self._selected))
            self.update()


# ──────────────────────────────────────────────────────────────────────────────
# TileSplitterPage — full-page 2-panel tile splitting tool
# ──────────────────────────────────────────────────────────────────────────────

class TileSplitterPage(QWidget):
    """Full-page tile splitter: left=image list+settings, right=interactive preview."""

    tiles_created = pyqtSignal(list)  # same contract as TileEditorWidget

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loaded_images: List[Tuple[Image.Image, str]] = []
        self._init_ui()

    def _init_ui(self):
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([420, 780])

        root.addWidget(splitter)
        self.setLayout(root)

    # ── left panel ──────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Load buttons
        load_row = QHBoxLayout()
        btn_single = QPushButton("Load Image")
        btn_single.clicked.connect(self._load_single)
        load_row.addWidget(btn_single)
        btn_multi = QPushButton("Load Multiple")
        btn_multi.clicked.connect(self._load_multiple)
        load_row.addWidget(btn_multi)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_images)
        load_row.addWidget(btn_clear)
        layout.addLayout(load_row)

        # Images table
        lbl = QLabel("Loaded Images (click row to preview)")
        lbl.setStyleSheet("font-size: 11px; color: #9ba8c0;")
        layout.addWidget(lbl)

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
        self.images_table.selectionModel().currentRowChanged.connect(self._on_image_row_changed)
        layout.addWidget(self.images_table, stretch=1)

        # Settings
        settings_group = QGroupBox("Split Settings")
        sg_layout = QVBoxLayout()
        sg_layout.setSpacing(4)

        # Grid mode
        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 100); self.rows_spin.setValue(4)
        self.rows_spin.setMaximumWidth(55)
        self.rows_spin.valueChanged.connect(self._on_grid_changed)
        grid_row.addWidget(self.rows_spin)
        grid_row.addWidget(QLabel("×"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 100); self.cols_spin.setValue(4)
        self.cols_spin.setMaximumWidth(55)
        self.cols_spin.valueChanged.connect(self._on_grid_changed)
        grid_row.addWidget(self.cols_spin)
        self.row_base_chk = QCheckBox("Row-major")
        self.row_base_chk.setChecked(True)
        grid_row.addWidget(self.row_base_chk)
        self.split_grid_btn = QPushButton("Split by Grid")
        self.split_grid_btn.clicked.connect(self._split_by_grid)
        grid_row.addWidget(self.split_grid_btn)
        sg_layout.addLayout(grid_row)

        # Size mode
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Tile:"))
        self.tile_w_spin = QSpinBox()
        self.tile_w_spin.setRange(1, 10000); self.tile_w_spin.setValue(32)
        self.tile_w_spin.setMaximumWidth(55)
        self.tile_w_spin.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.tile_w_spin)
        size_row.addWidget(QLabel("×"))
        self.tile_h_spin = QSpinBox()
        self.tile_h_spin.setRange(1, 10000); self.tile_h_spin.setValue(32)
        self.tile_h_spin.setMaximumWidth(55)
        self.tile_h_spin.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.tile_h_spin)
        self.split_size_btn = QPushButton("Split by Size")
        self.split_size_btn.clicked.connect(self._split_by_size)
        size_row.addWidget(self.split_size_btn)
        sg_layout.addLayout(size_row)

        settings_group.setLayout(sg_layout)
        layout.addWidget(settings_group)

        # Select all / deselect all
        sel_row = QHBoxLayout()
        btn_all = QPushButton("Select All Tiles")
        btn_all.clicked.connect(lambda: self.preview.select_all())
        sel_row.addWidget(btn_all)
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(lambda: self.preview.deselect_all())
        sel_row.addWidget(btn_none)
        layout.addLayout(sel_row)

        # Result label
        self.result_label = QLabel("")
        layout.addWidget(self.result_label)

        panel.setLayout(layout)
        return panel

    # ── right panel ─────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel("Tile Preview  (click cell to toggle selection)")
        lbl.setStyleSheet("font-size: 11px; color: #9ba8c0;")
        layout.addWidget(lbl)

        self.preview = TilePreviewWidget()
        layout.addWidget(self.preview, stretch=1)

        panel.setLayout(layout)
        return panel

    # ── slots ────────────────────────────────────────────────────

    def _load_single(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            self._load_path(path)

    def _load_multiple(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
        for p in paths:
            self._load_path(p)

    def _load_path(self, path: str):
        try:
            img = Image.open(path)
            self.loaded_images.append((img, path))
            self._refresh_table()
            # Auto-select newly added row
            self.images_table.selectRow(len(self.loaded_images) - 1)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")

    def _clear_images(self):
        self.loaded_images.clear()
        self._refresh_table()
        self.preview.set_image(None)

    def _refresh_table(self):
        self.images_table.setRowCount(0)
        for i, (img, path) in enumerate(self.loaded_images):
            self.images_table.insertRow(i)
            # Preview icon
            thumb = self._make_thumb(img, 48, 48)
            pi = QTableWidgetItem()
            pi.setData(Qt.ItemDataRole.DecorationRole, thumb)
            pi.setFlags(pi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 0, pi)
            # Filename
            ni = QTableWidgetItem(Path(path).name)
            ni.setFlags(ni.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 1, ni)
            # Size
            si = QTableWidgetItem(f"{img.width}×{img.height}")
            si.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            si.setFlags(si.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.images_table.setItem(i, 2, si)
            self.images_table.setRowHeight(i, 54)

    def _on_image_row_changed(self, current, _previous):
        row = current.row()
        if 0 <= row < len(self.loaded_images):
            img, _ = self.loaded_images[row]
            self.preview.set_image(img)
            # Update grid based on current settings
            self.preview.set_grid(self.rows_spin.value(), self.cols_spin.value())

    def _on_grid_changed(self):
        self.preview.set_grid(self.rows_spin.value(), self.cols_spin.value())

    def _on_size_changed(self):
        """Recalculate grid from tile size for the currently selected image."""
        row = self.images_table.currentRow()
        if 0 <= row < len(self.loaded_images):
            img, _ = self.loaded_images[row]
            tw = max(1, self.tile_w_spin.value())
            th = max(1, self.tile_h_spin.value())
            rows = max(1, img.height // th)
            cols = max(1, img.width // tw)
            self.preview.set_grid(rows, cols)

    def _get_selected_image_rows(self) -> List[int]:
        return sorted({idx.row() for idx in self.images_table.selectedIndexes()})

    def _split_by_grid(self):
        from ..core.image_loader import ImageLoader
        selected_rows = self._get_selected_image_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Select at least one image!")
            return
        positions = self.preview.get_selected_positions()
        if not positions:
            QMessageBox.warning(self, "Warning", "Select at least one tile in the preview!")
            return
        rows = self.rows_spin.value()
        cols = self.cols_spin.value()
        row_base = self.row_base_chk.isChecked()
        try:
            tiles = []
            for img_idx in selected_rows:
                img, path = self.loaded_images[img_idx]
                stem = Path(path).stem
                split = ImageLoader.split_into_tiles(img, rows, cols, row_base=row_base)
                for r, c in positions:
                    ti = r * cols + c
                    if ti < len(split):
                        tiles.append((split[ti], stem))
            if not tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles for selected positions!")
                return
            self.result_label.setText(f"✓ {len(tiles)} tiles added to material library")
            self.result_label.setStyleSheet(f"color: {_T.SUCCESS};")
            self.tiles_created.emit(tiles)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Split failed:\n{e}")
            self.result_label.setText(f"✗ {e}")
            self.result_label.setStyleSheet(f"color: {_T.ERROR};")

    def _split_by_size(self):
        from ..core.image_loader import ImageLoader
        selected_rows = self._get_selected_image_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Select at least one image!")
            return
        positions = self.preview.get_selected_positions()
        if not positions:
            QMessageBox.warning(self, "Warning", "Select at least one tile in the preview!")
            return
        tw = self.tile_w_spin.value()
        th = self.tile_h_spin.value()
        try:
            tiles = []
            for img_idx in selected_rows:
                img, path = self.loaded_images[img_idx]
                stem = Path(path).stem
                split = ImageLoader.split_by_tile_size(img, tw, th)
                cols = img.width // tw
                for r, c in positions:
                    ti = r * cols + c
                    if ti < len(split):
                        tiles.append((split[ti], stem))
            if not tiles:
                QMessageBox.warning(self, "Warning", "No valid tiles for selected positions!")
                return
            self.result_label.setText(f"✓ {len(tiles)} tiles added to material library")
            self.result_label.setStyleSheet(f"color: {_T.SUCCESS};")
            self.tiles_created.emit(tiles)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Split failed:\n{e}")
            self.result_label.setText(f"✗ {e}")
            self.result_label.setStyleSheet(f"color: {_T.ERROR};")

    @staticmethod
    def _make_thumb(pil_image: Image.Image, w: int, h: int) -> QPixmap:
        img = pil_image.copy()
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
