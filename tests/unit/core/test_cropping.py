"""Unit tests for crop geometry and post-export cropping."""
import pytest
from PIL import Image

from src.core.cropping import (CropError, crop_animation_file, is_noop,
                                      pixel_box)

FULL = (0.0, 0.0, 1.0, 1.0)


# ── is_noop ──────────────────────────────────────────────────────────────

def test_none_and_full_frame_are_noops():
    assert is_noop(None) is True
    assert is_noop(FULL) is True


def test_partial_crop_is_not_a_noop():
    assert is_noop((0.1, 0.0, 0.9, 1.0)) is False
    assert is_noop((0.0, 0.0, 1.0, 0.5)) is False


# ── pixel_box ────────────────────────────────────────────────────────────

def test_pixel_box_covers_the_whole_image_for_a_full_crop():
    assert pixel_box(200, 100, FULL) == (0, 0, 200, 100)


def test_pixel_box_scales_to_the_image():
    assert pixel_box(200, 100, (0.5, 0.25, 0.25, 0.5)) == (100, 25, 150, 75)


def test_pixel_box_is_clamped_inside_the_image():
    left, top, right, bottom = pixel_box(100, 100, (0.9, 0.9, 0.5, 0.5))
    assert 0 <= left < right <= 100
    assert 0 <= top < bottom <= 100


def test_pixel_box_never_produces_an_empty_region():
    left, top, right, bottom = pixel_box(50, 50, (0.5, 0.5, 0.0001, 0.0001))
    assert right > left and bottom > top


# ── crop_animation_file ──────────────────────────────────────────────────

def _make_gif(path, size=(40, 20), frames=3):
    imgs = []
    for i in range(frames):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        # A distinctive block in the left half so cropping is observable. Each
        # frame differs, otherwise the GIF encoder legitimately merges them.
        im.paste(Image.new("RGBA", (size[0] // 2, size[1]), (255, 40 * i, 0, 255)), (0, 0))
        imgs.append(im.convert("P"))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=80, loop=0)
    return path


def test_crops_a_gif_in_place(tmp_path):
    gif = _make_gif(tmp_path / "a.gif")
    crop_animation_file(gif, (0.0, 0.0, 0.5, 1.0))
    with Image.open(gif) as im:
        assert im.size == (20, 20)
        assert getattr(im, "n_frames", 1) == 3


def test_crop_preserves_frame_timing(tmp_path):
    gif = _make_gif(tmp_path / "b.gif")
    crop_animation_file(gif, (0.0, 0.0, 0.5, 0.5))
    with Image.open(gif) as im:
        assert im.info.get("duration") == 80


def test_noop_crop_leaves_the_file_untouched(tmp_path):
    gif = _make_gif(tmp_path / "c.gif")
    before = gif.read_bytes()
    crop_animation_file(gif, FULL)
    assert gif.read_bytes() == before


def test_crop_keeps_the_expected_content(tmp_path):
    """Cropping to the right half should drop the red block entirely."""
    path = tmp_path / "d.gif"
    im = Image.new("RGBA", (40, 20), (0, 0, 255, 255))
    im.paste(Image.new("RGBA", (20, 20), (255, 0, 0, 255)), (0, 0))
    im.convert("P").save(path)

    crop_animation_file(path, (0.5, 0.0, 0.5, 1.0))
    with Image.open(path) as out:
        rgb = out.convert("RGB")
        assert rgb.size == (20, 20)
        assert rgb.getpixel((10, 10))[2] > 200   # blue half survived
        assert rgb.getpixel((10, 10))[0] < 60    # red half is gone


def test_missing_file_raises(tmp_path):
    with pytest.raises(CropError):
        crop_animation_file(tmp_path / "nope.gif", (0.0, 0.0, 0.5, 0.5))


def test_unsupported_extension_raises(tmp_path):
    weird = tmp_path / "x.tiff"
    Image.new("RGB", (10, 10)).save(weird)
    with pytest.raises(CropError):
        crop_animation_file(weird, (0.0, 0.0, 0.5, 0.5))


def test_video_crop_without_ffmpeg_reports_clearly(tmp_path, monkeypatch):
    import src.core.cropping as cropping
    fake = tmp_path / "v.mp4"
    fake.write_bytes(b"not really a video")
    monkeypatch.setattr(cropping.shutil, "which", lambda *_a, **_k: None)
    with pytest.raises(CropError) as exc:
        crop_animation_file(fake, (0.0, 0.0, 0.5, 0.5))
    assert "ffmpeg" in str(exc.value).lower()
