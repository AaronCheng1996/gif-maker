import os
from PIL import Image
from src.core.image_loader import ImageLoader, MaterialManager


def test_load_image_rgba(make_temp_image):
    p = make_temp_image(mode='RGB')
    img = ImageLoader.load_image(p)
    assert img.mode == 'RGBA'


def test_load_gif_frames_static(make_temp_image, tmp_path):
    # Save a static GIF
    p = tmp_path / "static.gif"
    Image.new('RGBA', (6, 4), (10, 20, 30, 255)).convert('P').save(p, format='GIF')
    frames = ImageLoader.load_gif_frames(str(p))
    assert len(frames) == 1
    f0, dur = frames[0]
    assert f0.mode == 'RGBA' and isinstance(dur, int)


def test_load_gif_frames_animated(make_temp_gif):
    p = make_temp_gif(frames=3, durations=(50, 60, 70))
    frames = ImageLoader.load_gif_frames(p)
    assert len(frames) == 3
    assert all(img.mode == 'RGBA' for img, _ in frames)


def test_split_into_tiles():
    img = Image.new('RGBA', (8, 6), (0, 0, 0, 0))
    tiles = ImageLoader.split_into_tiles(img, rows=3, cols=4)
    assert len(tiles) == 12
    assert all(t.size == (2, 2) for t in tiles)


def test_split_by_tile_size():
    img = Image.new('RGBA', (10, 6), (0, 0, 0, 0))
    tiles = ImageLoader.split_by_tile_size(img, tile_width=5, tile_height=3)
    assert len(tiles) == 4
    assert all(t.size == (5, 3) for t in tiles)


def test_material_manager_add_and_len(rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="a", duration=120)
    assert len(mm) == 1
    img, nm = mm.get_material(0)
    assert nm == "a" and img.mode == 'RGBA'


def test_material_manager_remove_and_clear(rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, duration=100)
    mm.add_material(rgb_image_small, duration=110)
    mm.remove_material(0)
    assert len(mm) == 1
    mm.clear()
    assert len(mm) == 0


def test_material_manager_load_from_gif(make_temp_gif):
    mm = MaterialManager()
    p = make_temp_gif(frames=2)
    mm.load_from_gif(p)
    assert len(mm) == 2


