"""
Integration tests for Auto Layout features
"""

import pytest
from PIL import Image
from src.core.image_loader import MaterialManager
from src.core.layer_timeline import LayerTimelineEditor, LayerFrame
from src.core.group_manager import GroupManager
from src.core.material_group import MaterialGroup


class MockMainWindow:
    """Mock main window with auto layout methods for testing"""
    def __init__(self):
        self.material_manager = MaterialManager()
        self.layer_timeline_editor = LayerTimelineEditor()
        self.group_manager = GroupManager()
        self.output_width = 100
        self.output_height = 100
    
    def get_frame_material_size(self, frame):
        """Get the size of material referenced by a frame"""
        if frame.material_index is not None:
            result = self.material_manager.get_material(frame.material_index)
            if result:
                image, name = result  # MaterialManager returns (image, name) tuple
                return image.size
        elif frame.group_index is not None:
            group = self.group_manager.get_group(frame.group_index)
            if group and len(group.material_indices) > 0:
                max_w, max_h = 0, 0
                for mat_idx in group.material_indices:
                    result = self.material_manager.get_material(mat_idx)
                    if result:
                        image, name = result
                        max_w = max(max_w, image.width)
                        max_h = max(max_h, image.height)
                return (max_w, max_h) if max_w > 0 else None
        return None
    
    def get_all_materials_max_size(self):
        """Calculate maximum width and height across all materials in timeline"""
        max_width = 0
        max_height = 0
        
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is None:
                    continue
                size = self.get_frame_material_size(frame)
                if size:
                    max_width = max(max_width, size[0])
                    max_height = max(max_height, size[1])
        
        return max_width, max_height
    
    def auto_fit_output_size(self):
        """Auto-adjust output size to fit all materials"""
        max_width, max_height = self.get_all_materials_max_size()
        if max_width > 0 and max_height > 0:
            self.output_width = max_width
            self.output_height = max_height
            return True
        return False
    
    def align_all_left(self):
        """Align all frames to left (x = 0)"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is not None and (frame.material_index is not None or frame.group_index is not None):
                    frame.x = 0
    
    def align_all_center_horizontal(self):
        """Align all frames to horizontal center"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is None:
                    continue
                size = self.get_frame_material_size(frame)
                if size:
                    frame.x = (self.output_width - size[0]) // 2
    
    def align_all_right(self):
        """Align all frames to right"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is None:
                    continue
                size = self.get_frame_material_size(frame)
                if size:
                    frame.x = self.output_width - size[0]
    
    def align_all_top(self):
        """Align all frames to top (y = 0)"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is not None and (frame.material_index is not None or frame.group_index is not None):
                    frame.y = 0
    
    def align_all_middle_vertical(self):
        """Align all frames to vertical middle"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is None:
                    continue
                size = self.get_frame_material_size(frame)
                if size:
                    frame.y = (self.output_height - size[1]) // 2
    
    def align_all_bottom(self):
        """Align all frames to bottom"""
        for track in self.layer_timeline_editor.layer_tracks:
            for frame in track.frames:
                if frame is None:
                    continue
                size = self.get_frame_material_size(frame)
                if size:
                    frame.y = self.output_height - size[1]


def test_auto_fit_size_with_mixed_materials():
    """Test auto-fit size calculation with different-sized materials"""
    window = MockMainWindow()
    
    # Add materials of different sizes
    img1 = Image.new('RGB', (20, 20), (255, 0, 0))
    img2 = Image.new('RGB', (40, 30), (0, 255, 0))
    img3 = Image.new('RGB', (15, 35), (0, 0, 255))
    
    window.material_manager.add_material(img1, name="small")
    window.material_manager.add_material(img2, name="medium")
    window.material_manager.add_material(img3, name="tall")
    
    # Add to timeline
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(3, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=1, x=0, y=0)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[2] = LayerFrame(material_index=2, x=0, y=0)
    
    # Auto-fit should find max dimensions
    result = window.auto_fit_output_size()
    assert result is True
    assert window.output_width == 40  # Max width
    assert window.output_height == 35  # Max height


def test_auto_fit_size_with_groups():
    """Test auto-fit size with Material Groups"""
    window = MockMainWindow()
    
    # Add materials
    img1 = Image.new('RGB', (10, 10), (255, 0, 0))
    img2 = Image.new('RGB', (25, 15), (0, 255, 0))
    img3 = Image.new('RGB', (30, 20), (0, 0, 255))
    
    window.material_manager.add_material(img1, name="mat1")
    window.material_manager.add_material(img2, name="mat2")
    window.material_manager.add_material(img3, name="mat3")
    
    # Create group with materials [1, 2]
    group = MaterialGroup(
        material_indices=[1, 2],
        frame_duration=100,
        loop_count=2,
        name="Test Group"
    )
    window.group_manager.add_group(group)
    
    # Add to timeline: one material + one group
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(2, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[1] = LayerFrame(group_index=0, x=0, y=0)
    
    # Auto-fit should consider group's max material size
    result = window.auto_fit_output_size()
    assert result is True
    assert window.output_width == 30  # Max from group (img3)
    assert window.output_height == 20  # Max from group (img3)


def test_align_left():
    """Test left alignment sets all x to 0"""
    window = MockMainWindow()
    
    img = Image.new('RGB', (20, 20), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(2, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=50, y=30)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=0, x=100, y=40)
    
    window.align_all_left()
    
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].x == 0
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[1].x == 0
    # Y should remain unchanged
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].y == 30
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[1].y == 40


def test_align_center_horizontal():
    """Test horizontal center alignment"""
    window = MockMainWindow()
    window.output_width = 100
    
    img = Image.new('RGB', (20, 20), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    window.align_all_center_horizontal()
    
    # x should be (100 - 20) / 2 = 40
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].x == 40


def test_align_right():
    """Test right alignment"""
    window = MockMainWindow()
    window.output_width = 100
    
    img = Image.new('RGB', (20, 20), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    window.align_all_right()
    
    # x should be 100 - 20 = 80
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].x == 80


def test_align_top():
    """Test top alignment sets all y to 0"""
    window = MockMainWindow()
    
    img = Image.new('RGB', (20, 20), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=10, y=50)
    
    window.align_all_top()
    
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].y == 0
    # X should remain unchanged
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].x == 10


def test_align_middle_vertical():
    """Test vertical middle alignment"""
    window = MockMainWindow()
    window.output_height = 100
    
    img = Image.new('RGB', (20, 30), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    window.align_all_middle_vertical()
    
    # y should be (100 - 30) / 2 = 35
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].y == 35


def test_align_bottom():
    """Test bottom alignment"""
    window = MockMainWindow()
    window.output_height = 100
    
    img = Image.new('RGB', (20, 30), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    tl_idx = window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    window.layer_timeline_editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    window.align_all_bottom()
    
    # y should be 100 - 30 = 70
    assert window.layer_timeline_editor.layer_tracks[tl_idx].frames[0].y == 70


def test_align_with_empty_timeline():
    """Test alignment functions handle empty timeline gracefully"""
    window = MockMainWindow()
    
    # Create empty timeline
    window.layer_timeline_editor.add_layer_track("Main")
    window.layer_timeline_editor.add_timebase_frames(2, duration_ms=100)
    
    # Should not crash
    window.align_all_left()
    window.align_all_center_horizontal()
    window.align_all_right()
    window.align_all_top()
    window.align_all_middle_vertical()
    window.align_all_bottom()
    
    # Auto-fit should return False for empty timeline
    result = window.auto_fit_output_size()
    assert result is False


def test_align_with_multiple_tracks():
    """Test alignment works across multiple layer tracks"""
    window = MockMainWindow()
    window.output_width = 100
    
    img = Image.new('RGB', (20, 20), (255, 0, 0))
    window.material_manager.add_material(img, name="mat")
    
    # Create two tracks
    tl1 = window.layer_timeline_editor.add_layer_track("Track1")
    tl2 = window.layer_timeline_editor.add_layer_track("Track2")
    window.layer_timeline_editor.add_timebase_frames(1, duration_ms=100)
    
    window.layer_timeline_editor.layer_tracks[tl1].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    window.layer_timeline_editor.layer_tracks[tl2].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    window.align_all_center_horizontal()
    
    # Both tracks should be centered
    assert window.layer_timeline_editor.layer_tracks[tl1].frames[0].x == 40
    assert window.layer_timeline_editor.layer_tracks[tl2].frames[0].x == 40

