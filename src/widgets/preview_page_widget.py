from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QColor
from PIL import Image
from typing import List, Tuple


class PreviewPageWidget(QWidget):
    """專門的預覽頁面，提供更大的預覽空間"""
    
    back_requested = pyqtSignal()  # 請求返回主頁面
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.frames: List[Tuple[Image.Image, int]] = []  # (image, duration)
        self.current_frame_index = 0
        self.is_playing = False
        
        self.init_ui()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
    
    def init_ui(self):
        """初始化使用者介面"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 返回按鈕
        back_layout = QHBoxLayout()
        self.back_button = QPushButton("← 返回主頁")
        self.back_button.setMaximumHeight(25)
        self.back_button.clicked.connect(self.back_requested.emit)
        back_layout.addWidget(self.back_button)
        back_layout.addStretch()
        
        layout.addLayout(back_layout)
        
        # 標題
        title_label = QLabel("預覽")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title_label)
        
        # 控制按鈕
        control_layout = QHBoxLayout()
        control_layout.addStretch()
        
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setMaximumHeight(25)
        control_layout.addWidget(self.play_button)
        
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setMaximumHeight(25)
        control_layout.addWidget(self.stop_button)
        
        self.prev_button = QPushButton("⏮ Prev")
        self.prev_button.clicked.connect(self.prev_frame)
        self.prev_button.setMaximumHeight(25)
        control_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("⏭ Next")
        self.next_button.clicked.connect(self.manual_next_frame)
        self.next_button.setMaximumHeight(25)
        control_layout.addWidget(self.next_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # 預覽區域 - 佔用剩餘空間
        preview_container = QHBoxLayout()
        preview_container.addStretch()
        
        self.preview_label = QLabel("No Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel { 
                background-color: #e8e8e8; 
                border: 2px solid #ccc; 
            }
        """)
        self.preview_label.setMinimumSize(800, 600)  # 更大的最小尺寸
        
        preview_container.addWidget(self.preview_label)
        preview_container.addStretch()
        layout.addLayout(preview_container)
        
        # 資訊標籤
        info_layout = QHBoxLayout()
        info_layout.addStretch()
        
        self.info_label = QLabel("Frame: 0/0")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.info_label)
        
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        self.setLayout(layout)
    
    
    def set_frames(self, frames: List[Tuple[Image.Image, int]]):
        """設定要預覽的幀"""
        self.frames = frames
        self.current_frame_index = 0
        
        if self.frames:
            self.show_current_frame()
        else:
            self.preview_label.setText("No Frames")
            self.info_label.setText("Frame: 0/0")

    def set_background_color(self, color):
        """設定預覽頁面的背景顏色（只影響預覽）。

        參數可為 QColor、(r, g, b) 或十六進位字串 "#rrggbb"。
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
                border: 2px solid #ccc; 
            }}
        """)
    
    def show_current_frame(self):
        """顯示當前幀"""
        if not self.frames or self.current_frame_index >= len(self.frames):
            return
        
        pil_image, _ = self.frames[self.current_frame_index]
        pixmap = self.pil_to_pixmap(pil_image)
        
        # 計算預覽標籤的可用大小
        label_size = self.preview_label.size()
        available_width = label_size.width() - 40  # 留一些邊距
        available_height = label_size.height() - 40
        
        # 如果還沒有正確的尺寸，使用最小尺寸
        if available_width <= 0 or available_height <= 0:
            available_width = 760  # 800 - 40
            available_height = 560  # 600 - 40
        
        # 計算縮放比例以適應可用空間，同時保持長寬比
        original_width = pixmap.width()
        original_height = pixmap.height()
        
        scale_x = available_width / original_width
        scale_y = available_height / original_height
        scale = min(scale_x, scale_y)  # 使用較小的縮放比例以確保完全顯示
        
        # 對於小圖片，找到在可用空間內的最大整數倍縮放
        if scale > 1.0:
            # 找到最大的整數倍縮放，確保圖片仍在邊界內
            max_integer_scale = int(scale)
            if max_integer_scale * original_width <= available_width and max_integer_scale * original_height <= available_height:
                scale = max_integer_scale
            else:
                scale = 1.0
        
        # 計算新尺寸
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        # 縮放圖片並保持長寬比
        scaled_pixmap = pixmap.scaled(
            new_width, 
            new_height, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.preview_label.setPixmap(scaled_pixmap)
        self.update_info()
    
    def pil_to_pixmap(self, pil_image: Image.Image) -> QPixmap:
        """將 PIL 圖片轉換為 QPixmap，支援透明度"""
        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')
        
        data = pil_image.tobytes('raw', 'RGBA')
        qimage = QImage(
            data,
            pil_image.width,
            pil_image.height,
            QImage.Format.Format_RGBA8888
        )
        
        return QPixmap.fromImage(qimage)
    
    def toggle_play(self):
        """切換播放/暫停狀態"""
        if self.is_playing:
            self.pause()
        else:
            self.play()
    
    def play(self):
        """開始播放動畫"""
        if not self.frames:
            return
        
        self.is_playing = True
        self.play_button.setText("⏸ Pause")
        
        if self.current_frame_index < len(self.frames):
            _, duration = self.frames[self.current_frame_index]
            self.timer.start(duration)
    
    def pause(self):
        """暫停播放"""
        self.is_playing = False
        self.play_button.setText("▶ Play")
        self.timer.stop()
    
    def stop(self):
        """停止播放並回到第一幀"""
        self.pause()
        self.current_frame_index = 0
        self.show_current_frame()
    
    def next_frame(self):
        """自動播放時切換到下一幀"""
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self.show_current_frame()
        
        if self.is_playing:
            _, duration = self.frames[self.current_frame_index]
            self.timer.start(duration)
    
    def manual_next_frame(self):
        """手動切換到下一幀"""
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self.show_current_frame()
    
    def prev_frame(self):
        """切換到上一幀"""
        if not self.frames:
            return
        
        self.current_frame_index = (self.current_frame_index - 1) % len(self.frames)
        self.show_current_frame()
    
    def update_info(self):
        """更新資訊標籤"""
        if self.frames:
            total = len(self.frames)
            current = self.current_frame_index + 1
            _, duration = self.frames[self.current_frame_index]
            self.info_label.setText(f"Frame: {current}/{total} | Duration: {duration}ms")
        else:
            self.info_label.setText("Frame: 0/0")
    
    def resizeEvent(self, event):
        """視窗大小改變時重新調整預覽圖片"""
        super().resizeEvent(event)
        if self.frames:
            # 延遲重新顯示以確保新的尺寸已生效
            QTimer.singleShot(50, self.show_current_frame)
