"""Tests for the GIF to Video tab, driven against the widget directly."""
import pytest
from PIL import Image

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core import gif_to_mp4
from src.core.video_to_gif import is_ffmpeg_available
from src.widgets.gif_to_mp4_widget import GifToMp4Widget

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


@pytest.fixture()
def widget(qapp):
    w = GifToMp4Widget()
    yield w
    # Qt aborts the process if a QThread outlives its widget.
    w.stop_workers()


def _gif(path, transparent=True, frames=6, size=(64, 48)):
    made = []
    for i in range(frames):
        frame = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else (10, 10, 10, 255))
        block = Image.new("RGBA", (20, 20), (200, 40 + i * 20, 60, 255))
        frame.paste(block, (4 + i * 4, 8))
        made.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=64))
    kwargs = dict(save_all=True, append_images=made[1:], duration=80, loop=0, disposal=2)
    if transparent:
        kwargs["transparency"] = 0
    made[0].save(path, **kwargs)
    return path


@pytest.fixture()
def clear_gif(tmp_path):
    return _gif(tmp_path / "clear.gif", transparent=True)


@pytest.fixture()
def solid_gif(tmp_path):
    return _gif(tmp_path / "solid.gif", transparent=False)


def _sized(w, qapp, width=1200, height=800):
    """Lay the widget out without a real window; show() faults in this environment."""
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    w.resize(width, height)
    qapp.processEvents()
    return w


def test_starts_empty(widget):
    assert widget.sources == []
    assert widget.file_list.count() == 0
    assert widget.convert_btn.isEnabled() is False


def test_adding_files_reports_what_is_in_them(widget, clear_gif, solid_gif, qapp):
    widget.add_paths([str(clear_gif), str(solid_gif)])
    qapp.processEvents()

    assert widget.file_list.count() == 2
    by_name = {s.path.name: s for s in widget.sources}
    assert by_name["clear.gif"].transparent is True
    assert by_name["solid.gif"].transparent is False
    assert by_name["clear.gif"].frames == 6
    assert by_name["clear.gif"].width == 64
    assert "1 with transparency" in widget.summary_label.text()


def test_the_same_file_is_not_queued_twice(widget, clear_gif, qapp):
    widget.add_paths([str(clear_gif), str(clear_gif)])
    qapp.processEvents()
    assert widget.file_list.count() == 1


def test_an_unreadable_file_is_flagged_and_excluded(widget, tmp_path, qapp):
    bad = tmp_path / "broken.gif"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n not really anything")
    widget.add_paths([str(bad)])
    qapp.processEvents()

    assert widget.sources[0].error
    assert "unreadable" in widget.file_list.item(0).text()
    assert "1 unreadable" in widget.summary_label.text()
    # Nothing usable, so there is nothing to convert.
    assert widget.convert_btn.isEnabled() is False


def test_removing_and_clearing(widget, clear_gif, solid_gif, qapp):
    widget.add_paths([str(clear_gif), str(solid_gif)])
    qapp.processEvents()
    widget.file_list.item(0).setSelected(True)
    widget.remove_selected()
    assert widget.file_list.count() == 1
    widget.clear_files()
    assert widget.file_list.count() == 0 and widget.sources == []


# ── the transparency decision, which is the point of the preview ─────────

def test_preview_shows_the_background_that_will_be_baked_in(widget, clear_gif, qapp):
    _sized(widget, qapp)
    widget.add_paths([str(clear_gif)])
    widget.file_list.setCurrentRow(0)
    qapp.processEvents()

    assert "become white" in widget.preview_note.text()
    pixmap = widget.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()

    widget.bg_combo.setCurrentIndex(1)      # black
    qapp.processEvents()
    assert "become black" in widget.preview_note.text()


def test_preview_says_nothing_about_a_background_for_an_opaque_file(widget, solid_gif, qapp):
    _sized(widget, qapp)
    widget.add_paths([str(solid_gif)])
    widget.file_list.setCurrentRow(0)
    qapp.processEvents()
    assert "no transparency" in widget.preview_note.text()


def test_choosing_vp9_keeps_transparency_and_disables_the_colour(widget, clear_gif, qapp):
    _sized(widget, qapp)
    widget.add_paths([str(clear_gif)])
    widget.file_list.setCurrentRow(0)
    widget.codec_combo.setCurrentText(gif_to_mp4.VP9_ALPHA)
    qapp.processEvents()

    assert "transparency is kept" in widget.preview_note.text()
    assert widget.bg_combo.isEnabled() is False
    assert "webm" in widget.dest_label.text()


def test_destination_extension_follows_the_codec(widget, qapp):
    widget.codec_combo.setCurrentText(gif_to_mp4.H264)
    qapp.processEvents()
    assert ".mp4" in widget.dest_label.text()
    widget.codec_combo.setCurrentText(gif_to_mp4.VP9_ALPHA)
    qapp.processEvents()
    assert ".webm" in widget.dest_label.text()


def test_output_folder_choice_is_reflected(widget, tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    widget.choose_output_folder()
    assert str(tmp_path) in widget.dest_label.text()
    widget.use_source_folder()
    assert "beside each source" in widget.dest_label.text()


# ── conversion ───────────────────────────────────────────────────────────

@needs_ffmpeg
def test_converting_writes_one_video_per_readable_file(widget, clear_gif, solid_gif,
                                                       tmp_path, monkeypatch, qapp):
    bad = tmp_path / "broken.gif"
    bad.write_bytes(b"not a gif")
    out = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))

    widget.add_paths([str(clear_gif), str(solid_gif), str(bad)])
    widget.choose_output_folder()
    qapp.processEvents()
    widget.convert()
    assert widget._worker.wait(120000)
    qapp.processEvents()

    assert sorted(p.name for p in out.glob("*.mp4")) == ["clear.mp4", "solid.mp4"]
    assert "0 failed" in widget.status_label.text()


@needs_ffmpeg
def test_the_chosen_quality_reaches_the_encoder(widget, clear_gif, tmp_path,
                                                monkeypatch, qapp):
    """A coarser preset has to produce a smaller file than a fine one."""
    sizes = []
    for index in (0, 4):                     # near-identical, then smallest
        out = tmp_path / f"q{index}"
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
        widget.clear_files()
        widget.add_paths([str(clear_gif)])
        widget.choose_output_folder()
        widget.quality_combo.setCurrentIndex(index)
        qapp.processEvents()
        widget.convert()
        assert widget._worker.wait(120000)
        qapp.processEvents()
        sizes.append((out / "clear.mp4").stat().st_size)
    assert sizes[1] < sizes[0]


@needs_ffmpeg
def test_a_failure_is_reported_rather_than_silently_dropped(widget, clear_gif, tmp_path,
                                                            monkeypatch, qapp):
    from src.core.video_to_gif import VideoConversionError

    def boom(*a, **k):
        raise VideoConversionError("encoder exploded")

    monkeypatch.setattr(gif_to_mp4, "convert_to_video", boom)
    out = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    widget.add_paths([str(clear_gif)])
    widget.choose_output_folder()
    widget.convert()
    assert widget._worker.wait(120000)
    qapp.processEvents()

    assert "1 failed" in widget.status_label.text()


def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()


# ── saying what the settings actually are ────────────────────────────────

def test_the_recipe_line_states_the_defaults(widget, qapp):
    text = widget.recipe_label.text()
    assert "MP4 (H.264)" in text
    assert "Balanced" in text
    assert "original size kept" in text
    assert "transparent → white" in text
    assert "saved beside each source" in text


def test_the_recipe_follows_the_codec(widget, qapp):
    widget.codec_combo.setCurrentText(gif_to_mp4.VP9_ALPHA)
    qapp.processEvents()
    text = widget.recipe_label.text()
    assert "WebM (VP9)" in text
    assert "transparency kept" in text
    assert "transparent →" not in text


def test_the_recipe_follows_the_quality_and_background(widget, qapp):
    widget.quality_combo.setCurrentIndex(0)
    widget.bg_combo.setCurrentIndex(1)          # black
    qapp.processEvents()
    text = widget.recipe_label.text()
    assert "Near-identical" in text
    assert "transparent → black" in text


def test_the_recipe_follows_the_output_folder(widget, tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    widget.choose_output_folder()
    qapp.processEvents()
    assert str(tmp_path) in widget.recipe_label.text()


# ── size handling, which is what a width box gets wrong ──────────────────

def test_by_default_no_width_limit_is_applied(widget, clear_gif, qapp):
    widget.add_paths([str(clear_gif)])
    qapp.processEvents()
    assert widget.width_cap() == 0
    assert widget.sources[0].output_size(0) == (64, 48)
    # No arrow in the row: nothing is being resized.
    assert "→" not in widget.file_list.item(0).text()


def test_a_width_limit_never_enlarges(widget, clear_gif, qapp):
    """The spinbox sits at 800; a 64px GIF must not be blown up to it."""
    widget.add_paths([str(clear_gif)])
    widget.resize_checkbox.setChecked(True)
    qapp.processEvents()
    assert widget.width_cap() == 800
    assert widget.sources[0].output_size(800) == (64, 48)
    assert "→" not in widget.file_list.item(0).text()


def test_a_width_limit_shrinks_and_the_row_says_so(widget, tmp_path, qapp):
    """The spinbox floor is 64px, so the source has to be wider than that."""
    wide = _gif(tmp_path / "wide.gif", transparent=False, size=(256, 192))
    widget.add_paths([str(wide)])
    widget.resize_checkbox.setChecked(True)
    widget.width_spinbox.setValue(128)
    qapp.processEvents()

    assert widget.width_cap() == 128
    assert widget.sources[0].output_size(128) == (128, 96)
    assert "256×192 → 128×96" in widget.file_list.item(0).text()
    assert "shrink to 128px if wider" in widget.recipe_label.text()


def test_output_size_is_rounded_down_to_even(widget, tmp_path, qapp):
    """4:2:0 cannot hold an odd edge, so it is dropped — and shown as dropped."""
    odd = _gif(tmp_path / "odd.gif", transparent=False, size=(65, 49))
    widget.add_paths([str(odd)])
    qapp.processEvents()
    assert widget.sources[0].output_size(0) == (64, 48)
    assert "65×49 → 64×48" in widget.file_list.item(0).text()


@needs_ffmpeg
def test_the_advertised_size_is_the_size_produced(widget, clear_gif, tmp_path,
                                                  monkeypatch, qapp):
    """Whatever the row promises has to be what lands on disk."""
    out = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    widget.add_paths([str(clear_gif)])
    widget.resize_checkbox.setChecked(True)
    widget.width_spinbox.setValue(800)          # larger than the source
    widget.choose_output_folder()
    qapp.processEvents()
    promised = widget.sources[0].output_size(widget.width_cap())

    widget.convert()
    assert widget._worker.wait(120000)
    qapp.processEvents()
    info = gif_to_mp4.get_animation_info(out / "clear.mp4")
    assert (info["width"], info["height"]) == promised
