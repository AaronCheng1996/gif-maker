import io
import os
import json
import tempfile
import contextlib
import typing as t
import pytest
from PIL import Image


@pytest.fixture()
def tmp_gif_path(tmp_path):
    return tmp_path / "out.gif"


@pytest.fixture()
def rgba_image_small() -> Image.Image:
    # 8x8 RGBA with a transparent background and a white square in center
    img = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    for x in range(2, 6):
        for y in range(2, 6):
            img.putpixel((x, y), (255, 255, 255, 255))
    return img


@pytest.fixture()
def rgb_image_small() -> Image.Image:
    return Image.new('RGB', (8, 8), (10, 20, 30))


@pytest.fixture()
def tiny_rgba() -> Image.Image:
    return Image.new('RGBA', (2, 1), (200, 100, 0, 128))


@pytest.fixture()
def make_temp_image(tmp_path):
    def _make(size=(10, 10), color=(100, 150, 200, 255), mode='RGBA'):
        img = Image.new(mode, size, color)
        p = tmp_path / "img.png"
        img.save(p)
        return str(p)
    return _make


@pytest.fixture()
def make_temp_gif(tmp_path):
    def _make(frames=3, size=(6, 4), durations=(100, 120, 140)):
        images = []
        for i in range(frames):
            img = Image.new('RGBA', size, (i * 40 % 255, i * 80 % 255, i * 120 % 255, 255))
            images.append(img.convert('P'))
        p = tmp_path / "anim.gif"
        images[0].save(p, format='GIF', save_all=True, append_images=images[1:], duration=list(durations)[:frames], loop=0, optimize=True, disposal=2)
        return str(p)
    return _make


