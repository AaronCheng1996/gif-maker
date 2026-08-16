"""Tests for the Crop GIF tab."""
import pytest
from PIL import Image

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.widgets.crop_gif_widget import CropGifWidget


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


def test_video_files_report_no_preview(widget, qapp, tmp_path, monkeypatch):
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"stub")
    _add(widget, qapp, monkeypatch, [fake])
    assert widget.source_size is None
    assert "video" in widget.preview.text().lower()


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
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    widget.spin_x.setValue(8)
    widget.spin_w.setValue(40)
    qapp.processEvents()
    x, _y, w, _h = widget.preview.crop_rect()
    assert round(x, 3) == 0.1
    assert round(w, 3) == 0.5


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
