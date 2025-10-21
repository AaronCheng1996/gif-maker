from PIL import Image
from src.core.gif_builder import GifBuilder
from src.core.image_loader import MaterialManager
from src.core.sequence_editor import SequenceEditor
from src.core.multi_timeline import MultiTimelineEditor, TimelineFrame


def test_build_from_sequence_solid_bg(tmp_gif_path, rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="a", duration=90)
    # Second material slightly different color to prevent optimization collapsing frames
    different = Image.new('RGB', rgb_image_small.size, (11, 21, 31))
    mm.add_material(different, name="b", duration=110)
    se = SequenceEditor()
    se.add_frame(0, 90)
    se.add_frame(1, 110)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 0, 0, 255)
    gb.build_from_sequence(mm, se, output_path=str(tmp_gif_path))
    info = gb.get_gif_info(str(tmp_gif_path))
    assert info['frame_count'] == 2
    assert info['has_transparency'] is False


def test_resize_and_info(tmp_path, rgba_image_small):
    # Prepare a small gif first
    gb = GifBuilder()
    gb.set_output_size(12, 10)
    gb.set_background_color(0, 0, 0, 0)
    out = tmp_path / "a.gif"
    img1 = rgba_image_small.copy()
    img2 = rgba_image_small.copy()
    img2.putpixel((0, 0), (0, 255, 0, 255))
    gb.build_from_images([img1, img2], durations=[50, 50], output_path=str(out))

    resized = tmp_path / "a_small.gif"
    gb.resize_gif(str(out), str(resized), scale_factor=0.5)
    info = gb.get_gif_info(str(resized))
    assert info['frame_count'] == 2
    assert info['size'][0] == 6 and info['size'][1] == 5


def test_build_from_multitimeline(tmp_gif_path, rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="a")
    mm.add_material(rgb_image_small, name="b")

    ed = MultiTimelineEditor()
    tl_a = ed.add_timeline("A")
    tl_b = ed.add_timeline("B")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.timelines[tl_a].frames[0] = TimelineFrame(material_index=0, x=0, y=0)
    ed.timelines[tl_b].frames[1] = TimelineFrame(material_index=1, x=1, y=1)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(0, 0, 0, 0)
    gb.build_from_multitimeline(ed, mm, output_path=str(tmp_gif_path))
    info = gb.get_gif_info(str(tmp_gif_path))
    assert info['frame_count'] == 2


