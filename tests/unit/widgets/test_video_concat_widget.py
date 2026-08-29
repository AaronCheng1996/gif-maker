"""Tests for the Video Concat tab, driven against the widget directly."""
import pytest
from PIL import Image, ImageDraw

from PyQt6.QtWidgets import QApplication, QFileDialog

from src.core import concat
from src.widgets.video_concat_widget import VideoConcatWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def widget(qapp):
    w = VideoConcatWidget()
    yield w
    w.stop_workers()


def _make_gif(path, size=(160, 120), frames=6, rgb=(200, 40, 40)):
    images = []
    for i in range(frames):
        im = Image.new("RGB", size, rgb)
        ImageDraw.Draw(im).rectangle([i * 3, 0, i * 3 + 4, 4], fill=(255, 255, 255))
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=100, loop=0)
    return path


def _add(widget, qapp, monkeypatch, paths):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: ([str(p) for p in paths], "")))
    widget.add_files()
    qapp.processEvents()


# ── the clip list ────────────────────────────────────────────────────────

def test_clips_are_listed_in_the_order_they_will_play(widget, qapp, tmp_path,
                                                      monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    assert [c.path.name for c in widget.clips] == ["a.gif", "b.gif"]
    assert widget.list.count() == 2
    assert widget.list.item(0).text().startswith("1.")


def test_the_same_file_is_not_queued_twice(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a, a])
    assert len(widget.clips) == 1


def test_files_it_cannot_join_are_ignored(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    _add(widget, qapp, monkeypatch, [a, junk])
    assert [c.path.name for c in widget.clips] == ["a.gif"]


def test_a_clip_can_be_moved_because_order_is_the_whole_point(widget, qapp,
                                                              tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    c = _make_gif(tmp_path / "c.gif")
    _add(widget, qapp, monkeypatch, [a, b, c])

    widget.list.setCurrentRow(2)
    widget._move(-1)
    assert [x.path.name for x in widget.clips] == ["a.gif", "c.gif", "b.gif"]
    assert widget.list.currentRow() == 1, "the moved clip stays selected"

    widget.list.setCurrentRow(0)
    widget._move(-1)
    assert [x.path.name for x in widget.clips] == ["a.gif", "c.gif", "b.gif"], \
        "moving past the top does nothing"


def test_removing_and_clearing(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])

    widget.list.setCurrentRow(0)
    widget.list.item(0).setSelected(True)
    widget.remove_selected()
    assert [x.path.name for x in widget.clips] == ["b.gif"]

    widget.clear_clips()
    assert widget.clips == []
    assert widget.list.count() == 0


# ── what it says it will do ──────────────────────────────────────────────

def test_one_clip_is_not_offered_as_a_join(widget, qapp, tmp_path, monkeypatch):
    _add(widget, qapp, monkeypatch, [_make_gif(tmp_path / "a.gif")])
    assert "two" in widget.recipe.text().lower()
    assert not widget.join_btn.isEnabled()


def test_the_summary_states_the_frame_it_will_produce(widget, qapp, tmp_path,
                                                      monkeypatch):
    a = _make_gif(tmp_path / "a.gif", size=(160, 120))
    b = _make_gif(tmp_path / "b.gif", size=(100, 200))
    _add(widget, qapp, monkeypatch, [a, b])
    text = widget.recipe.text()
    assert "160" in text and "120" in text
    assert "2 clips" in text
    assert "padded" in text, "the clip that gets bars should be called out"


def test_choosing_to_fit_the_largest_changes_the_frame(widget, qapp, tmp_path,
                                                       monkeypatch):
    a = _make_gif(tmp_path / "a.gif", size=(160, 120))
    b = _make_gif(tmp_path / "b.gif", size=(100, 200))
    _add(widget, qapp, monkeypatch, [a, b])

    widget.size_combo.setCurrentText(concat.MATCH_LARGEST)
    qapp.processEvents()
    plan = widget.current_plan()
    assert (plan["width"], plan["height"]) == (160, 200)


def test_the_destination_is_named_after_the_first_clip(widget, qapp, tmp_path,
                                                       monkeypatch):
    a = _make_gif(tmp_path / "opening.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])

    assert widget.destination().name == "opening_joined.mp4"
    widget.format_combo.setCurrentText(concat.GIF)
    assert widget.destination().name == "opening_joined.gif"


def test_the_destination_follows_a_chosen_folder(widget, qapp, tmp_path,
                                                 monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])

    out = tmp_path / "elsewhere"
    out.mkdir()
    widget.output_dir = str(out)
    assert widget.destination().parent == out


# ── shutdown ─────────────────────────────────────────────────────────────

def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()
