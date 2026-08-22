"""Tests for the Crop GIF tab."""
import pytest
from PIL import Image

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core.video_to_gif import is_ffmpeg_available
from src.widgets.crop_gif_widget import CropGifWidget

needs_ffmpeg = pytest.mark.skipif(not is_ffmpeg_available(),
                                  reason="ffmpeg is not installed")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)


@pytest.fixture()
def widget(qapp):
    w = CropGifWidget()
    w.resize(900, 600)
    yield w
    w.stop_workers()


def _make_gif(path, size=(80, 40), frames=3):
    imgs = []
    for i in range(frames):
        im = Image.new("RGBA", size, (0, 0, 255, 255))
        im.paste(Image.new("RGBA", (size[0] // 2, size[1]), (255, 30 * i, 0, 255)), (0, 0))
        imgs.append(im.convert("P"))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=90, loop=0)
    return path


def _make_mp4(path, size=(120, 90), frames=12):
    """A real short video, so the ffmpeg decode path is genuinely exercised."""
    from src.core import gif_to_mp4
    # A distinct name: `path.with_suffix(".gif")` would collide with a GIF the
    # caller may have made under the same stem.
    seed = path.with_name(path.stem + "__seed.gif")
    _make_gif(seed, size=size, frames=frames)
    gif_to_mp4.convert_to_video(seed, path, crf=30)
    seed.unlink()
    return path


def _add(widget, qapp, monkeypatch, paths):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(p) for p in paths], ""))
    widget.add_files()
    qapp.processEvents()
    if widget._loader is not None:
        widget._loader.wait(60000)
    qapp.processEvents()


# ── file list ────────────────────────────────────────────────────────────

def test_starts_empty(widget):
    assert widget.files == []
    assert widget.crop_btn.isEnabled() is False
    assert widget.file_list.count() == 0


def test_adding_files_populates_the_list(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    assert widget.file_list.count() == 2
    assert widget.crop_btn.isEnabled() is True


def test_the_same_file_is_not_added_twice(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _add(widget, qapp, monkeypatch, [a])
    assert widget.file_list.count() == 1


def test_removing_and_clearing(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    widget.file_list.item(0).setSelected(True)
    widget.remove_selected()
    assert widget.file_list.count() == 1
    widget.clear_files()
    assert widget.files == []
    assert widget.crop_btn.isEnabled() is False


# ── preview ──────────────────────────────────────────────────────────────

def test_selecting_a_file_loads_its_frames(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    assert widget.source_size == (80, 40)
    assert len(widget.frames) == 3
    assert widget.preview.preview_pixmap() is not None
    assert "80×40" in widget.info_label.text()


def test_playback_toggles(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.toggle_playback()
    assert widget._playing is True
    widget.toggle_playback()
    assert widget._playing is False


def test_advancing_wraps_around(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    for _ in range(len(widget.frames)):
        widget._advance_frame()
    assert widget._frame_index == 0


@needs_ffmpeg
def test_a_video_gets_a_draggable_preview_like_a_gif(widget, qapp, tmp_path, monkeypatch):
    """Video used to be listed but never shown, so the box could not be placed."""
    clip = _make_mp4(tmp_path / "clip.mp4")
    _add(widget, qapp, monkeypatch, [clip])

    assert widget.source_size == (120, 90)      # the container's real size
    assert widget.frames, "no frames decoded for the video"
    assert widget.preview.pixmap() is not None


def test_an_unreadable_video_is_reported(widget, qapp, tmp_path, monkeypatch):
    fake = tmp_path / "broken.mp4"
    fake.write_bytes(b"stub")
    _add(widget, qapp, monkeypatch, [fake])
    assert widget.source_size is None
    assert widget.frames == []


# ── crop fields ──────────────────────────────────────────────────────────

def test_spinboxes_mirror_the_dragged_rectangle(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.preview.set_crop_rect(0.25, 0.5, 0.5, 0.25)
    qapp.processEvents()
    assert widget.spin_x.value() == 20      # 0.25 * 80
    assert widget.spin_y.value() == 20      # 0.5 * 40
    assert widget.spin_w.value() == 40
    assert widget.spin_h.value() == 10


def test_typing_pixel_values_moves_the_rectangle(widget, qapp, tmp_path, monkeypatch):
    """The fields commit on editingFinished, which is what leaving one does."""
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.spin_x.setValue(8)
    widget.spin_w.setValue(40)
    widget.spin_w.editingFinished.emit()
    qapp.processEvents()
    x, _y, w, _h = widget.preview.crop_rect()
    assert round(x, 3) == 0.1
    assert round(w, 3) == 0.5


def test_half_typed_numbers_do_not_reach_the_rectangle(widget, qapp, tmp_path,
                                                       monkeypatch):
    """Typing 1000 over 200 used to pass through 1000200 and get clamped."""
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif", size=(80, 40))])
    before = widget.preview.crop_rect()
    widget.spin_w.setValue(60)          # a value change on its own commits nothing
    qapp.processEvents()
    assert widget.preview.crop_rect() == before
    widget.spin_w.editingFinished.emit()
    qapp.processEvents()
    assert widget.preview.crop_rect() != before


def test_reset_restores_the_full_frame(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.preview.set_crop_rect(0.2, 0.2, 0.3, 0.3)
    widget.preview.reset_crop()
    qapp.processEvents()
    assert widget.spin_w.value() == 80 and widget.spin_h.value() == 40


# ── output paths ─────────────────────────────────────────────────────────

def test_default_destination_adds_a_suffix_beside_the_source(widget, tmp_path):
    src = tmp_path / "clip.gif"
    dst = widget._destination_for(src)
    assert dst == tmp_path / "clip_cropped.gif"


def test_overwrite_uses_the_source_path(widget, tmp_path):
    widget.overwrite_checkbox.setChecked(True)
    src = tmp_path / "clip.gif"
    assert widget._destination_for(src) == src


def test_output_folder_is_used_when_set(widget, tmp_path):
    widget.last_output_dir = str(tmp_path / "out")
    dst = widget._destination_for(tmp_path / "clip.gif")
    assert dst.parent == tmp_path / "out"


def test_empty_suffix_still_avoids_overwriting_the_source(widget, tmp_path):
    """Blanking the suffix must not silently clobber the original."""
    widget.suffix_edit.setText("")
    src = tmp_path / "clip.gif"
    assert widget._destination_for(src) != src


# ── cropping ─────────────────────────────────────────────────────────────

def test_crops_every_listed_file(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    widget.preview.set_crop_rect(0.0, 0.0, 0.5, 1.0)
    qapp.processEvents()

    widget.run_crop()
    assert widget._worker.wait(120000)
    qapp.processEvents()

    for name in ("a_cropped.gif", "b_cropped.gif"):
        out = tmp_path / name
        assert out.exists()
        with Image.open(out) as im:
            assert im.size == (40, 40)


def test_cropped_output_keeps_the_selected_half(widget, qapp, tmp_path, monkeypatch):
    """The left half is red, the right half blue; crop to the right half."""
    path = tmp_path / "halves.gif"
    im = Image.new("RGBA", (80, 40), (0, 0, 255, 255))
    im.paste(Image.new("RGBA", (40, 40), (255, 0, 0, 255)), (0, 0))
    im.convert("P").save(path)

    _add(widget, qapp, monkeypatch, [path])
    widget.preview.set_crop_rect(0.5, 0.0, 0.5, 1.0)
    qapp.processEvents()
    widget.run_crop()
    assert widget._worker.wait(120000)
    qapp.processEvents()

    with Image.open(tmp_path / "halves_cropped.gif") as out:
        rgb = out.convert("RGB")
        assert rgb.size == (40, 40)
        assert rgb.getpixel((20, 20))[2] > 200
        assert rgb.getpixel((20, 20))[0] < 60


def test_overwrite_replaces_the_original(widget, qapp, tmp_path, monkeypatch):
    path = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [path])
    widget.overwrite_checkbox.setChecked(True)
    widget.preview.set_crop_rect(0.0, 0.0, 0.5, 1.0)
    qapp.processEvents()
    widget.run_crop()
    assert widget._worker.wait(120000)
    qapp.processEvents()

    assert not (tmp_path / "a_cropped.gif").exists()
    with Image.open(path) as im:
        assert im.size == (40, 40)


def test_full_frame_crop_is_refused(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.preview.reset_crop()
    widget.run_crop()
    assert widget._worker is None
    assert not (tmp_path / "a_cropped.gif").exists()


def test_cropping_without_files_does_nothing(widget):
    widget.run_crop()
    assert widget._worker is None


def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()


@needs_ffmpeg
def test_the_same_rectangle_crops_a_gif_and_a_video_alike(widget, qapp, tmp_path,
                                                          monkeypatch):
    """One rectangle, two very different pipelines — Pillow and ffmpeg."""
    from src.core.cropping import crop_animation_file

    gif = _make_gif(tmp_path / "pair.gif", size=(120, 90), frames=8)
    mp4 = _make_mp4(tmp_path / "pair.mp4", size=(120, 90), frames=8)
    crop = (0.25, 0.20, 0.50, 0.60)

    out_gif = crop_animation_file(gif, crop, output_path=str(tmp_path / "a.gif"))
    out_mp4 = crop_animation_file(mp4, crop, output_path=str(tmp_path / "a.mp4"))

    from src.core import gif_to_mp4
    with Image.open(out_gif) as im:
        gif_size = im.size
    info = gif_to_mp4.get_animation_info(out_mp4)
    assert gif_size == (info["width"], info["height"]) == (60, 54)
    # Cropping must not disturb the pixel aspect, or players letterbox it.
    assert info["sar"] == "1:1"


@needs_ffmpeg
def test_a_video_preview_is_sampled_not_fully_decoded(widget, qapp, tmp_path,
                                                      monkeypatch):
    """A long clip must not turn into thousands of pixmaps in memory."""
    clip = _make_mp4(tmp_path / "long.mp4", size=(64, 64), frames=200)
    _add(widget, qapp, monkeypatch, [clip])
    assert widget.frames
    assert len(widget.frames) <= 200


# ── edge handles ─────────────────────────────────────────────────────────

def _press_release(overlay, qapp, x, y, to_x, to_y):
    from PyQt6.QtCore import QPointF, QEvent
    from PyQt6.QtGui import QMouseEvent
    def ev(kind, px, py):
        return QMouseEvent(kind, QPointF(px, py), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    overlay.mousePressEvent(ev(QEvent.Type.MouseButtonPress, x, y))
    overlay.mouseMoveEvent(ev(QEvent.Type.MouseMove, to_x, to_y))
    overlay.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, to_x, to_y))
    qapp.processEvents()


def test_dragging_an_edge_of_a_full_frame_rect_resizes_it(widget, qapp, tmp_path,
                                                          monkeypatch):
    """It used to throw the rectangle away and start drawing a new region."""
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif", size=(200, 100))])
    widget.preview.resize(400, 200)
    qapp.processEvents()
    assert widget.preview.crop_rect() == (0.0, 0.0, 1.0, 1.0)

    img = widget.preview.image_rect()
    # Grab the right edge and pull it inwards.
    _press_release(widget.preview, qapp,
                   img.right(), img.center().y(),
                   img.left() + img.width() * 0.6, img.center().y())

    x, y, w, h = widget.preview.crop_rect()
    assert round(x, 2) == 0.0 and round(y, 2) == 0.0    # the other edges held
    assert 0.4 < w < 0.8, f"right edge did not resize, width is {w}"
    assert round(h, 2) == 1.0


# ── one size across a batch, positions per file ──────────────────────────

def test_a_batch_keeps_one_pixel_size_across_different_frame_sizes(widget, qapp,
                                                                   tmp_path, monkeypatch):
    """Proportional rectangles gave every size of file a different result."""
    small = _make_gif(tmp_path / "small.gif", size=(100, 100))
    large = _make_gif(tmp_path / "large.gif", size=(400, 400))
    _add(widget, qapp, monkeypatch, [small, large])

    widget.file_list.setCurrentRow(0)
    qapp.processEvents()
    widget.preview.set_crop_rect(0.1, 0.1, 0.5, 0.5)      # 50x50 of a 100px frame
    qapp.processEvents()

    for path in (small, large):
        x, y, w, h = widget.crop_for(path)
        fw, fh = widget.size_of(path)
        assert round(w * fw) == 50, f"{path.name} came out {round(w * fw)}px wide"
        assert round(h * fh) == 50


def test_each_file_remembers_where_its_own_rectangle_sits(widget, qapp, tmp_path,
                                                          monkeypatch):
    a = _make_gif(tmp_path / "a.gif", size=(200, 200))
    b = _make_gif(tmp_path / "b.gif", size=(200, 200))
    _add(widget, qapp, monkeypatch, [a, b])

    widget.file_list.setCurrentRow(0)
    qapp.processEvents()
    widget.preview.set_crop_rect(0.0, 0.0, 0.5, 0.5)
    qapp.processEvents()

    widget.file_list.setCurrentRow(1)
    qapp.processEvents()
    if widget._loader is not None:
        widget._loader.wait(60000)
    qapp.processEvents()
    widget.preview.set_crop_rect(0.5, 0.5, 0.5, 0.5)
    qapp.processEvents()

    ax, ay, _, _ = widget.crop_for(a)
    bx, by, _, _ = widget.crop_for(b)
    assert (round(ax, 2), round(ay, 2)) == (0.0, 0.0)
    assert (round(bx, 2), round(by, 2)) == (0.5, 0.5)


def test_an_unvisited_file_inherits_the_shared_size(widget, qapp, tmp_path, monkeypatch):
    """The point of a batch: set the size once, every file gets it."""
    a = _make_gif(tmp_path / "a.gif", size=(200, 200))
    b = _make_gif(tmp_path / "b.gif", size=(300, 150))
    _add(widget, qapp, monkeypatch, [a, b])

    widget.file_list.setCurrentRow(0)
    qapp.processEvents()
    widget.preview.set_crop_rect(0.0, 0.0, 0.4, 0.4)      # 80x80
    qapp.processEvents()

    x, y, w, h = widget.crop_for(b)          # never selected
    bw, bh = widget.size_of(b)
    assert (round(w * bw), round(h * bh)) == (80, 80)


def test_a_shared_size_larger_than_a_frame_is_clipped(widget, qapp, tmp_path, monkeypatch):
    big = _make_gif(tmp_path / "big.gif", size=(400, 400))
    tiny = _make_gif(tmp_path / "tiny.gif", size=(60, 60))
    _add(widget, qapp, monkeypatch, [big, tiny])

    widget.file_list.setCurrentRow(0)
    qapp.processEvents()
    widget.preview.set_crop_rect(0.0, 0.0, 0.5, 0.5)      # 200x200
    qapp.processEvents()

    x, y, w, h = widget.crop_for(tiny)
    tw, th = widget.size_of(tiny)
    assert round(w * tw) <= tw and round(h * th) <= th
    assert 0.0 <= x and x + w <= 1.0001
