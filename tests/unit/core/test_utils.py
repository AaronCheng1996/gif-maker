from PIL import Image
import pytest
from src.core.utils import ensure_rgba, resize_image, create_background, paste_center, validate_image_file


def test_ensure_rgba_converts_from_rgb(rgb_image_small):
    out = ensure_rgba(rgb_image_small)
    assert out.mode == 'RGBA'


def test_ensure_rgba_noop_when_already_rgba(rgba_image_small):
    out = ensure_rgba(rgba_image_small)
    assert out.mode == 'RGBA'
    assert out.size == rgba_image_small.size


def test_resize_image_keep_aspect(rgb_image_small):
    out = resize_image(rgb_image_small.copy(), (4, 4), keep_aspect=True)
    assert out.size[0] <= 4 and out.size[1] <= 4


def test_resize_image_force_size(rgb_image_small):
    out = resize_image(rgb_image_small.copy(), (5, 3), keep_aspect=False)
    assert out.size == (5, 3)


def test_create_background_with_alpha():
    bg = create_background((7, 5), (1, 2, 3, 4))
    assert bg.size == (7, 5)
    assert bg.mode == 'RGBA'
    assert bg.getpixel((0, 0)) == (1, 2, 3, 4)


def test_paste_center_positions():
    bg = create_background((10, 10), (0, 0, 0, 0))
    fg = Image.new('RGBA', (4, 2), (255, 255, 255, 255))
    out = paste_center(bg, fg)
    # Check center pixel is white
    assert out.getpixel((5, 5))[3] > 0


def test_validate_image_file(make_temp_image):
    p = make_temp_image(size=(3, 3))
    assert validate_image_file(p) is True


