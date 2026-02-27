from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QMouseEvent, QColor
from PIL import Image
from typing import List, Tuple

from .theme import AppTheme as _T


class ClickableLabel(QLabel):
    """可點擊的 QLabel"""
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PreviewWidget(QWidget):
    # Signal to emit frame info: (current_frame, total_frames, duration)
    frame_info_changed = pyqtSignal(int, int, int)
    # Signal to emit when preview image is clicked for fullscreen
    preview_clicked = pyqtSignal()
    
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
        
        # Preview area — expands to fill available space; image is scaled+centered manually
        self.preview_label = ClickableLabel("No Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setMinimumSize(80, 80)
        self.preview_label.setStyleSheet(f"""
            QLabel {{ 
                background-color: {_T.CARD}; 
                border: 2px solid {_T.BORDER}; 
            }}
            QLabel:hover {{
                border: 2px solid {_T.BORDER_FOCUS};
                background-color: {_T.ELEVATED};
            }}
        """)
        self.preview_label.clicked.connect(self.on_preview_clicked)
        layout.addWidget(self.preview_label, 1)  # stretch=1 → fills remaining height
        
        self.setLayout(layout)
    
    def set_background_color(self, color):
        """Set the preview area's background color (preview-only).

        Accepts QColor, (r, g, b) tuple, or hex string like "#rrggbb".
        """
        if isinstance(color, QColor):
            qcolor = color
        elif isinstance(color, tuple) and len(color) >= 3:
            qcolor = QColor(color[0], color[1], color[2])
        elif isinstance(color, str):
            qcolor = QColor(color)
        else:
            return
        hex_color = qcolor.name()
        self.preview_label.setStyleSheet(f"""
            QLabel {{ 
                background-color: {hex_color}; 
                border: 2px solid {_T.BORDER}; 
            }}
            QLabel:hover {{
                border: 2px solid {_T.BORDER_FOCUS};
            }}
        """)
    
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

        avail_w = max(self.preview_label.width(), 80)
        avail_h = max(self.preview_label.height(), 80)
        orig_w, orig_h = pixmap.width(), pixmap.height()

        scale = min(avail_w / orig_w, avail_h / orig_h)

        # For small images prefer the largest integer upscale that still fits
        if scale > 1.0:
            int_scale = int(scale)
            if int_scale * orig_w <= avail_w and int_scale * orig_h <= avail_h:
                scale = int_scale
            else:
                scale = 1.0

        scaled_pixmap = pixmap.scaled(
            int(orig_w * scale),
            int(orig_h * scale),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled_pixmap)
        self.update_info()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.frames:
            self.show_current_frame()

    def go_to_frame(self, index: int):
        """Jump to a specific frame index without changing the timer state."""
        if not self.frames:
            return
        self.current_frame_index = index % len(self.frames)
        self.show_current_frame()
    
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
    
    def on_preview_clicked(self):
        """當預覽圖片被點擊時觸發"""
        if self.frames:  # 只有在有幀內容時才觸發
            self.preview_clicked.emit()
    

