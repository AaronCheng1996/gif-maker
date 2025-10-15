from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
from typing import List, Tuple


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.frames: List[Tuple[Image.Image, int]] = []  # (image, duration)
        self.current_frame_index = 0
        self.is_playing = False
        self.use_checkerboard = False  # Show checkerboard for transparency
        
        self.init_ui()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
    
    def set_checkerboard(self, enabled: bool):
        """Enable or disable checkerboard background for transparency preview"""
        self.use_checkerboard = enabled
        if self.frames:
            self.show_current_frame()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        self.preview_label = QLabel("No Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 400)
        self.preview_label.setStyleSheet("QLabel { background-color: #f0f0f0; border: 2px solid #ccc; }")
        layout.addWidget(self.preview_label)
        
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
        
        self.info_label = QLabel("Frame: 0/0")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        self.setLayout(layout)
    
    def set_frames(self, frames: List[Tuple[Image.Image, int]]):
        self.frames = frames
        self.current_frame_index = 0
        
        if self.frames:
            self.show_current_frame()
            self.update_info()
        else:
            self.preview_label.setText("No Frames")
            self.info_label.setText("Frame: 0/0")
    
    def show_current_frame(self):
        if not self.frames or self.current_frame_index >= len(self.frames):
            return
        
        pil_image, _ = self.frames[self.current_frame_index]
        
        pixmap = self.pil_to_pixmap(pil_image, self.use_checkerboard)
        
        scaled_pixmap = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.preview_label.setPixmap(scaled_pixmap)
        self.update_info()
    
    def pil_to_pixmap(self, pil_image: Image.Image, use_checkerboard: bool = False) -> QPixmap:
        """Convert PIL image to QPixmap, optionally with checkerboard background for transparency"""
        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')
        
        # If checkerboard requested and image has transparency, composite on checkerboard
        if use_checkerboard:
            # Create checkerboard background
            checker_size = 16
            width, height = pil_image.size
            checker = Image.new('RGB', (width, height), 'white')
            
            for y in range(0, height, checker_size):
                for x in range(0, width, checker_size):
                    if ((x // checker_size) + (y // checker_size)) % 2 == 1:
                        for dy in range(min(checker_size, height - y)):
                            for dx in range(min(checker_size, width - x)):
                                checker.putpixel((x + dx, y + dy), (204, 204, 204))
            
            # Composite image on checkerboard
            checker = checker.convert('RGBA')
            checker.paste(pil_image, (0, 0), pil_image)
            pil_image = checker
        
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
        if self.frames:
            total = len(self.frames)
            current = self.current_frame_index + 1
            _, duration = self.frames[self.current_frame_index]
            self.info_label.setText(f"Frame: {current}/{total} | Duration: {duration}ms")
        else:
            self.info_label.setText("Frame: 0/0")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.frames:
            self.show_current_frame()

