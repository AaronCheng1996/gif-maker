from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
from typing import List, Tuple


class PreviewWidget(QWidget):
    # Signal to emit frame info: (current_frame, total_frames, duration)
    frame_info_changed = pyqtSignal(int, int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.frames: List[Tuple[Image.Image, int]] = []  # (image, duration)
        self.current_frame_index = 0
        self.is_playing = False
        
        self.init_ui()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)  # Add spacing between elements

        control_layout = QHBoxLayout()
        
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_button)
        
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self.stop)
        control_layout.addWidget(self.stop_button)
        
        self.prev_button = QPushButton("⏮ Prev")
        self.prev_button.clicked.connect(self.prev_frame)
        control_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("⏭ Next")
        self.next_button.clicked.connect(self.manual_next_frame)
        control_layout.addWidget(self.next_button)
        
        layout.addLayout(control_layout)
        
        # Preview area - Fixed 400x400 size
        self.preview_label = QLabel("No Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(400, 400)  # Fixed size to prevent UI layout issues
        self.preview_label.setScaledContents(False)  # Don't auto-scale, we'll handle it manually
        # Light gray background to make transparent areas visible, but not distracting
        self.preview_label.setStyleSheet("QLabel { background-color: #e8e8e8; border: 2px solid #ccc; }")
        layout.addWidget(self.preview_label)
        
        self.setLayout(layout)
    
    def set_frames(self, frames: List[Tuple[Image.Image, int]]):
        self.frames = frames
        self.current_frame_index = 0
        
        if self.frames:
            self.show_current_frame()
        else:
            self.preview_label.setText("No Frames")
            self.frame_info_changed.emit(0, 0, 0)
    
    def show_current_frame(self):
        if not self.frames or self.current_frame_index >= len(self.frames):
            return
        
        pil_image, _ = self.frames[self.current_frame_index]
        
        pixmap = self.pil_to_pixmap(pil_image)
        
        # Calculate scaling to fit within 400x400 while maintaining aspect ratio
        max_size = 400
        original_width = pixmap.width()
        original_height = pixmap.height()
        
        # Calculate scale factor to fit within the square
        scale_x = max_size / original_width
        scale_y = max_size / original_height
        scale = min(scale_x, scale_y)  # Use the smaller scale to ensure it fits
        
        # Calculate new dimensions
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        # Scale the pixmap while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            new_width, 
            new_height, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Set the scaled pixmap - Qt will center it due to AlignCenter alignment
        self.preview_label.setPixmap(scaled_pixmap)
        self.update_info()
    
    def pil_to_pixmap(self, pil_image: Image.Image) -> QPixmap:
        """Convert PIL image to QPixmap with transparency support"""
        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')
        
        # Direct conversion - much faster, no checkerboard overhead
        data = pil_image.tobytes('raw', 'RGBA')
        
        qimage = QImage(
            data,
            pil_image.width,
            pil_image.height,
            QImage.Format.Format_RGBA8888
        )
        
        return QPixmap.fromImage(qimage)
    
    def toggle_play(self):
        if self.is_playing:
            self.pause()
        else:
            self.play()
    
    def play(self):
        if not self.frames:
            return
        
        self.is_playing = True
        self.play_button.setText("⏸ Pause")
        
        if self.current_frame_index < len(self.frames):
            _, duration = self.frames[self.current_frame_index]
            self.timer.start(duration)
    
    def pause(self):
        self.is_playing = False
        self.play_button.setText("▶ Play")
        self.timer.stop()
    
    def stop(self):
        self.pause()
        self.current_frame_index = 0
        self.show_current_frame()
    
    def next_frame(self):
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self.show_current_frame()
        
        if self.is_playing:
            _, duration = self.frames[self.current_frame_index]
            self.timer.start(duration)
    
    def manual_next_frame(self):
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self.show_current_frame()
    
    def prev_frame(self):
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index - 1) % len(self.frames)
        self.show_current_frame()
    
    def update_info(self):
        """Emit signal with current frame info"""
        if self.frames:
            total = len(self.frames)
            current = self.current_frame_index + 1
            _, duration = self.frames[self.current_frame_index]
            self.frame_info_changed.emit(current, total, duration)
        else:
            self.frame_info_changed.emit(0, 0, 0)
    

