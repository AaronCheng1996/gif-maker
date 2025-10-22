"""Unit tests for GifBuilder chroma key (green screen) functionality"""
import pytest
from PIL import Image
from src.core.gif_builder import GifBuilder
from src.core.image_loader import MaterialManager
from src.core.multi_timeline import MultiTimelineEditor, TimelineFrame


@pytest.fixture
def green_screen_image():
    """Create a test image with green background and red foreground"""
    img = Image.new('RGB', (20, 20), (0, 255, 0))  # Green background
    # Add a red square in the center
    for x in range(8, 12):
        for y in range(8, 12):
            img.putpixel((x, y), (255, 0, 0))  # Red foreground
    return img


@pytest.fixture
def blue_screen_image():
    """Create a test image with blue background and yellow foreground"""
    img = Image.new('RGB', (15, 15), (0, 0, 255))  # Blue background
    # Add a yellow circle-ish shape in the center
    for x in range(5, 10):
        for y in range(5, 10):
            img.putpixel((x, y), (255, 255, 0))  # Yellow foreground
    return img


@pytest.fixture
def gradient_image():
    """Create an image with color gradients for threshold testing"""
    img = Image.new('RGB', (30, 10), (0, 0, 0))
    # Create a gradient from pure green to slightly off-green
    for x in range(30):
        color_offset = x * 2  # Gradual change
        for y in range(10):
            img.putpixel((x, y), (color_offset, 255, color_offset))
    return img


class TestChromaKeySettings:
    """Test chroma key configuration methods"""
    
    def test_initial_state(self):
        """Test that chroma key is disabled by default"""
        gb = GifBuilder()
        assert gb.chroma_key_color is None
        assert gb.chroma_key_threshold == 30
    
    def test_set_chroma_key(self):
        """Test setting a chroma key color"""
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)  # Green
        assert gb.chroma_key_color == (0, 255, 0)
        assert gb.chroma_key_threshold == 30
    
    def test_set_chroma_key_with_custom_threshold(self):
        """Test setting chroma key with custom threshold"""
        gb = GifBuilder()
        gb.set_chroma_key(0, 0, 255, threshold=50)  # Blue with threshold 50
        assert gb.chroma_key_color == (0, 0, 255)
        assert gb.chroma_key_threshold == 50
    
    def test_clear_chroma_key(self):
        """Test clearing chroma key setting"""
        gb = GifBuilder()
        gb.set_chroma_key(255, 0, 0)  # Red
        assert gb.chroma_key_color is not None
        
        gb.clear_chroma_key()
        assert gb.chroma_key_color is None
    
    def test_multiple_set_operations(self):
        """Test changing chroma key color multiple times"""
        gb = GifBuilder()
        gb.set_chroma_key(255, 0, 0)  # Red
        assert gb.chroma_key_color == (255, 0, 0)
        
        gb.set_chroma_key(0, 255, 0)  # Green
        assert gb.chroma_key_color == (0, 255, 0)
        
        gb.set_chroma_key(0, 0, 255)  # Blue
        assert gb.chroma_key_color == (0, 0, 255)


class TestApplyChromaKey:
    """Test chroma key application to images"""
    
    def test_apply_chroma_key_disabled(self, green_screen_image):
        """Test that no chroma key is applied when disabled"""
        gb = GifBuilder()
        result = gb.apply_chroma_key(green_screen_image)
        
        # Should return RGBA version but with no transparency changes
        assert result.mode == 'RGBA'
        # Check that green pixels are still opaque
        r, g, b, a = result.getpixel((0, 0))
        assert (r, g, b) == (0, 255, 0)
        assert a == 255  # Fully opaque
    
    def test_apply_chroma_key_green_screen(self, green_screen_image):
        """Test removing green background"""
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)  # Target pure green
        
        result = gb.apply_chroma_key(green_screen_image)
        
        # Check that green background became transparent
        _, _, _, a = result.getpixel((0, 0))
        assert a == 0  # Should be transparent
        
        # Check that red foreground remains opaque
        r, g, b, a = result.getpixel((9, 9))
        assert (r, g, b) == (255, 0, 0)
        assert a == 255  # Should remain opaque
    
    def test_apply_chroma_key_blue_screen(self, blue_screen_image):
        """Test removing blue background"""
        gb = GifBuilder()
        gb.set_chroma_key(0, 0, 255)  # Target pure blue
        
        result = gb.apply_chroma_key(blue_screen_image)
        
        # Check that blue background became transparent
        _, _, _, a = result.getpixel((0, 0))
        assert a == 0  # Should be transparent
        
        # Check that yellow foreground remains opaque
        r, g, b, a = result.getpixel((7, 7))
        assert (r, g, b) == (255, 255, 0)
        assert a == 255  # Should remain opaque
    
    def test_threshold_effect(self, gradient_image):
        """Test that threshold affects which colors are made transparent"""
        # With strict threshold (0), only exact matches should be transparent
        gb_strict = GifBuilder()
        gb_strict.set_chroma_key(0, 255, 0, threshold=0)
        result_strict = gb_strict.apply_chroma_key(gradient_image)
        
        # Left pixel (pure green) should be transparent
        _, _, _, a_left = result_strict.getpixel((0, 5))
        assert a_left == 0
        
        # Right pixel (far from green) should be opaque
        _, _, _, a_right = result_strict.getpixel((29, 5))
        assert a_right == 255
        
        # With loose threshold (100), more colors should be transparent
        gb_loose = GifBuilder()
        gb_loose.set_chroma_key(0, 255, 0, threshold=100)
        result_loose = gb_loose.apply_chroma_key(gradient_image)
        
        # More pixels should be transparent with loose threshold
        transparent_count_strict = sum(
            1 for x in range(30) 
            if result_strict.getpixel((x, 5))[3] == 0
        )
        transparent_count_loose = sum(
            1 for x in range(30) 
            if result_loose.getpixel((x, 5))[3] == 0
        )
        
        assert transparent_count_loose > transparent_count_strict
    
    def test_rgba_input(self):
        """Test that RGBA images are handled correctly"""
        img = Image.new('RGBA', (10, 10), (0, 255, 0, 255))
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)
        
        result = gb.apply_chroma_key(img)
        
        assert result.mode == 'RGBA'
        _, _, _, a = result.getpixel((5, 5))
        assert a == 0  # Should be transparent
    
    def test_partial_transparency_preserved(self):
        """Test that non-matching colors with partial alpha are preserved"""
        img = Image.new('RGBA', (10, 10), (255, 0, 0, 128))  # Semi-transparent red
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)  # Target green
        
        result = gb.apply_chroma_key(img)
        
        # Red should remain unchanged
        r, g, b, a = result.getpixel((5, 5))
        assert (r, g, b) == (255, 0, 0)
        assert a == 128  # Alpha should be preserved


class TestChromaKeyInMultiTimeline:
    """Test chroma key integration with multi-timeline composition"""
    
    def test_multitimeline_with_chroma_key(self, tmp_path, green_screen_image):
        """Test that chroma key is applied during multi-timeline composition"""
        mm = MaterialManager()
        mm.add_material(green_screen_image, name="green_bg")
        
        ed = MultiTimelineEditor()
        tl_idx = ed.add_timeline("Main")
        ed.add_timebase_frames(1, duration_ms=100)
        ed.timelines[tl_idx].frames[0] = TimelineFrame(material_index=0, x=0, y=0)
        
        gb = GifBuilder()
        gb.set_output_size(20, 20)
        gb.set_background_color(255, 255, 255, 255)  # White background
        gb.set_chroma_key(0, 255, 0)  # Remove green
        
        # Compose frame
        composed = gb._compose_from_multi_timeline_frame(ed, mm, 0)
        
        # Green areas should show white background (transparent)
        r, g, b, _ = composed.getpixel((0, 0))
        # Background should show through where green was
        assert (r, g, b) == (255, 255, 255)
        
        # Red foreground should still be visible
        r, g, b, _ = composed.getpixel((9, 9))
        assert (r, g, b) == (255, 0, 0)
    
    def test_multitimeline_chroma_key_disabled(self, tmp_path, green_screen_image):
        """Test multi-timeline composition without chroma key"""
        mm = MaterialManager()
        mm.add_material(green_screen_image, name="green_bg")
        
        ed = MultiTimelineEditor()
        tl_idx = ed.add_timeline("Main")
        ed.add_timebase_frames(1, duration_ms=100)
        ed.timelines[tl_idx].frames[0] = TimelineFrame(material_index=0, x=0, y=0)
        
        gb = GifBuilder()
        gb.set_output_size(20, 20)
        gb.set_background_color(255, 255, 255, 255)
        # No chroma key set
        
        # Compose frame
        composed = gb._compose_from_multi_timeline_frame(ed, mm, 0)
        
        # Green should still be visible (not transparent)
        r, g, b, _ = composed.getpixel((0, 0))
        assert (r, g, b) == (0, 255, 0)
    
    def test_layered_composition_with_chroma_key(self, tmp_path, green_screen_image, blue_screen_image):
        """Test chroma key with multiple layers"""
        mm = MaterialManager()
        mm.add_material(green_screen_image, name="green")
        mm.add_material(blue_screen_image, name="blue")
        
        ed = MultiTimelineEditor()
        tl_a = ed.add_timeline("Layer1")
        tl_b = ed.add_timeline("Layer2")
        ed.add_timebase_frames(1, duration_ms=100)
        
        # Place both images on same frame
        ed.timelines[tl_a].frames[0] = TimelineFrame(material_index=0, x=0, y=0)
        ed.timelines[tl_b].frames[0] = TimelineFrame(material_index=1, x=5, y=5)
        
        gb = GifBuilder()
        gb.set_output_size(30, 30)
        gb.set_background_color(0, 0, 0, 255)  # Black background
        gb.set_chroma_key(0, 255, 0)  # Remove green
        
        # Compose frame
        composed = gb._compose_from_multi_timeline_frame(ed, mm, 0)
        
        # Where only green image was (now transparent), should show black background
        r, g, b, _ = composed.getpixel((0, 0))
        assert (r, g, b) == (0, 0, 0)
        
        # Where blue image is placed, should show blue (green removed from layer1)
        _, _, b, _ = composed.getpixel((7, 7))
        assert b > 200  # Should be blue-ish
    
    def test_export_gif_with_chroma_key(self, tmp_path, green_screen_image, blue_screen_image):
        """Test exporting GIF with chroma key applied"""
        mm = MaterialManager()
        mm.add_material(green_screen_image, name="green")
        mm.add_material(blue_screen_image, name="blue")
        
        ed = MultiTimelineEditor()
        tl_idx = ed.add_timeline("Main")
        ed.add_timebase_frames(2, duration_ms=100)
        ed.timelines[tl_idx].frames[0] = TimelineFrame(material_index=0, x=0, y=0)
        ed.timelines[tl_idx].frames[1] = TimelineFrame(material_index=1, x=0, y=0)  # Different frame
        
        gb = GifBuilder()
        gb.set_output_size(20, 20)
        gb.set_background_color(0, 0, 0, 0)  # Transparent background
        gb.set_chroma_key(0, 255, 0)  # Remove green
        
        output_path = tmp_path / "chroma_test.gif"
        gb.build_from_multitimeline(ed, mm, str(output_path))
        
        # Verify GIF was created successfully
        assert output_path.exists()
        assert output_path.stat().st_size > 0  # File has content
        
        # Verify basic GIF properties
        info = gb.get_gif_info(str(output_path))
        assert info['frame_count'] >= 1  # At least one frame
        assert info['size'] == (20, 20)  # Correct output size


class TestChromaKeyEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_image(self):
        """Test chroma key on minimal image"""
        img = Image.new('RGB', (1, 1), (0, 255, 0))
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)
        
        result = gb.apply_chroma_key(img)
        
        assert result.mode == 'RGBA'
        assert result.size == (1, 1)
        _, _, _, a = result.getpixel((0, 0))
        assert a == 0  # Should be transparent
    
    def test_no_matching_colors(self):
        """Test chroma key when no colors match"""
        img = Image.new('RGB', (10, 10), (255, 0, 0))  # All red
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)  # Target green
        
        result = gb.apply_chroma_key(img)
        
        # All pixels should remain opaque
        for x in range(10):
            for y in range(10):
                _, _, _, a = result.getpixel((x, y))
                assert a == 255  # Should remain opaque
    
    def test_all_matching_colors(self):
        """Test chroma key when all colors match"""
        img = Image.new('RGB', (10, 10), (0, 255, 0))  # All green
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0)  # Target green
        
        result = gb.apply_chroma_key(img)
        
        # All pixels should be transparent
        for x in range(10):
            for y in range(10):
                _, _, _, a = result.getpixel((x, y))
                assert a == 0  # Should be transparent
    
    def test_extreme_threshold_values(self):
        """Test behavior with extreme threshold values"""
        img = Image.new('RGB', (5, 5), (100, 100, 100))  # Gray
        
        # Threshold 0 - only exact matches
        gb_zero = GifBuilder()
        gb_zero.set_chroma_key(100, 100, 100, threshold=0)
        result_zero = gb_zero.apply_chroma_key(img)
        assert result_zero.getpixel((0, 0))[3] == 0  # Exact match, transparent
        
        # Very high threshold - should match everything
        gb_high = GifBuilder()
        gb_high.set_chroma_key(0, 0, 0, threshold=500)
        result_high = gb_high.apply_chroma_key(img)
        assert result_high.getpixel((0, 0))[3] == 0  # Should match due to high threshold
    
    def test_color_distance_calculation(self):
        """Test that color distance is calculated correctly"""
        img = Image.new('RGB', (3, 1), (0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0))    # Red - far from green
        img.putpixel((1, 0), (0, 255, 0))    # Green - exact match
        img.putpixel((2, 0), (10, 255, 10))  # Near green
        
        gb = GifBuilder()
        gb.set_chroma_key(0, 255, 0, threshold=20)  # Small threshold
        
        result = gb.apply_chroma_key(img)
        
        # Red should remain opaque (far from target)
        assert result.getpixel((0, 0))[3] == 255
        
        # Exact green should be transparent
        assert result.getpixel((1, 0))[3] == 0
        
        # Near green should also be transparent (within threshold)
        assert result.getpixel((2, 0))[3] == 0

