"""Tests for the Video Concat tab, driven against the widget directly."""
import pytest
from PIL import Image, ImageDraw

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog,
                             QMessageBox)

from src.core import concat
from src.widgets.video_concat_widget import (LIBRARY_ROW_MIME, TimelineList,
                                             VideoConcatWidget)


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


def _select_library(widget, row):
    widget.library_list.clearSelection()
    widget.library_list.setCurrentRow(row)
    widget.library_list.item(row).setSelected(True)


# ── the library ──────────────────────────────────────────────────────────

def test_files_land_in_the_library_not_on_the_timeline(widget, qapp, tmp_path,
                                                       monkeypatch):
    """Adding material and using it are separate acts."""
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    assert [p.name for p in widget.library] == ["a.gif"]
    assert widget.segments == []


def test_the_same_file_is_only_stocked_once(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a, a])
    assert len(widget.library) == 1


def test_files_it_cannot_join_are_ignored(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    _add(widget, qapp, monkeypatch, [a, junk])
    assert [p.name for p in widget.library] == ["a.gif"]


def test_forgetting_material_leaves_the_timeline_alone(widget, qapp, tmp_path,
                                                       monkeypatch):
    """A segment already placed is a use, not a reference to the library row."""
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    assert len(widget.segments) == 1

    _select_library(widget, 0)
    widget.forget_selected()
    assert widget.library == []
    assert len(widget.segments) == 1, "the placed segment should survive"


# ── the timeline ─────────────────────────────────────────────────────────

def test_material_can_be_placed_more_than_once(widget, qapp, tmp_path, monkeypatch):
    """The reason the two lists are separate: an intro reused as an outro."""
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    assert len(widget.segments) == 2
    assert widget.segments[0] is not widget.segments[1]


def test_dropping_from_the_library_inserts_where_it_was_dropped(widget, qapp,
                                                                tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _select_library(widget, 0)
    widget.add_selected_to_timeline()

    widget._on_library_dropped(1, 1)          # b.gif, between the two a.gifs
    assert [s.path.name for s in widget.segments] == ["a.gif", "b.gif", "a.gif"]


def test_a_segment_can_be_dragged_to_a_new_place(widget, qapp, tmp_path,
                                                 monkeypatch):
    for name in ("a.gif", "b.gif", "c.gif"):
        _make_gif(tmp_path / name)
    _add(widget, qapp, monkeypatch, [tmp_path / n for n in ("a.gif", "b.gif", "c.gif")])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()
    assert [s.path.name for s in widget.segments] == ["a.gif", "b.gif", "c.gif"]

    widget._on_segment_moved(0, 3)            # a.gif to the end
    assert [s.path.name for s in widget.segments] == ["b.gif", "c.gif", "a.gif"]


def test_the_timeline_accepts_both_kinds_of_drop(qapp):
    tl = TimelineList()
    assert tl.acceptDrops()
    assert tl.dragDropMode() == QAbstractItemView.DragDropMode.DragDrop


def test_the_library_hands_over_the_row_it_dragged(widget, qapp, tmp_path,
                                                   monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    b = _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    item = widget.library_list.item(1)
    mime = widget.library_list.mimeData([item])
    assert mime.hasFormat(LIBRARY_ROW_MIME)
    assert bytes(mime.data(LIBRARY_ROW_MIME)).decode() == "1"


def test_the_arrow_buttons_reorder(widget, qapp, tmp_path, monkeypatch):
    for name in ("a.gif", "b.gif"):
        _make_gif(tmp_path / name)
    _add(widget, qapp, monkeypatch, [tmp_path / "a.gif", tmp_path / "b.gif"])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()

    widget.timeline_list.setCurrentRow(1)
    widget._move(-1)
    assert [s.path.name for s in widget.segments] == ["b.gif", "a.gif"]
    assert widget.timeline_list.currentRow() == 0


def test_removing_and_clearing_the_timeline(widget, qapp, tmp_path, monkeypatch):
    for name in ("a.gif", "b.gif"):
        _make_gif(tmp_path / name)
    _add(widget, qapp, monkeypatch, [tmp_path / "a.gif", tmp_path / "b.gif"])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()

    widget.timeline_list.setCurrentRow(0)
    widget.remove_segment()
    assert [s.path.name for s in widget.segments] == ["b.gif"]

    widget.clear_timeline()
    assert widget.segments == []
    assert widget.library, "clearing the timeline must not empty the library"


# ── trimming ─────────────────────────────────────────────────────────────

def _timeline_of(widget, qapp, tmp_path, monkeypatch, count=2):
    names = [f"{chr(ord('a') + i)}.gif" for i in range(count)]
    for n in names:
        _make_gif(tmp_path / n)
    _add(widget, qapp, monkeypatch, [tmp_path / n for n in names])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()
    qapp.processEvents()
    return names


def test_typing_an_in_and_out_point_trims_the_segment(widget, qapp, tmp_path,
                                                      monkeypatch):
    _timeline_of(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()

    widget.start_spin.setValue(0.10)
    widget.end_spin.setValue(0.40)
    seg = widget.segments[0]
    assert seg.start == pytest.approx(0.10)
    assert seg.out_point == pytest.approx(0.40)
    assert seg.trimmed


def test_the_out_point_is_stored_as_open_ended_when_it_is_the_whole_clip(
        widget, qapp, tmp_path, monkeypatch):
    """So "to the end" keeps meaning that rather than freezing a number."""
    _timeline_of(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()
    seg = widget.segments[0]

    widget.end_spin.setValue(seg.source_duration)
    assert seg.end == 0.0
    assert not seg.trimmed


def test_trimming_one_use_leaves_the_other_alone(widget, qapp, tmp_path,
                                                 monkeypatch):
    """Trims belong to the segment, not to the file."""
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    qapp.processEvents()

    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()
    widget.start_spin.setValue(0.2)

    assert widget.segments[0].start == pytest.approx(0.2)
    assert widget.segments[1].start == 0.0


def test_the_whole_clip_can_be_put_back(widget, qapp, tmp_path, monkeypatch):
    _timeline_of(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()
    widget.start_spin.setValue(0.2)
    assert widget.segments[0].trimmed

    widget.reset_trim()
    assert not widget.segments[0].trimmed
    assert widget.segments[0].start == 0.0 and widget.segments[0].end == 0.0


def test_a_trimmed_segment_says_so_in_the_list(widget, qapp, tmp_path, monkeypatch):
    _timeline_of(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()
    widget.start_spin.setValue(0.2)
    assert "0.20s" in widget.timeline_list.item(0).text()


# ── what it says it will do ──────────────────────────────────────────────

def test_one_segment_is_not_offered_as_a_join(widget, qapp, tmp_path, monkeypatch):
    a = _make_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    assert "two" in widget.recipe.text().lower()
    assert not widget.join_btn.isEnabled()


def test_the_summary_states_the_frame_and_the_trims(widget, qapp, tmp_path,
                                                    monkeypatch):
    _make_gif(tmp_path / "a.gif", size=(160, 120))
    _make_gif(tmp_path / "b.gif", size=(100, 200))
    _add(widget, qapp, monkeypatch, [tmp_path / "a.gif", tmp_path / "b.gif"])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()
    qapp.processEvents()

    text = widget.recipe.text()
    assert "160" in text and "120" in text
    assert "2 segments" in text
    assert "padded" in text

    widget.timeline_list.setCurrentRow(0)
    qapp.processEvents()
    widget.start_spin.setValue(0.2)
    assert "trimmed" in widget.recipe.text()


def test_choosing_to_fit_the_largest_changes_the_frame(widget, qapp, tmp_path,
                                                       monkeypatch):
    _make_gif(tmp_path / "a.gif", size=(160, 120))
    _make_gif(tmp_path / "b.gif", size=(100, 200))
    _add(widget, qapp, monkeypatch, [tmp_path / "a.gif", tmp_path / "b.gif"])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()

    widget.size_combo.setCurrentText(concat.MATCH_LARGEST)
    qapp.processEvents()
    plan = widget.current_plan()
    assert (plan["width"], plan["height"]) == (160, 200)


def test_the_destination_is_named_after_the_first_segment(widget, qapp, tmp_path,
                                                          monkeypatch):
    _make_gif(tmp_path / "opening.gif")
    _make_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [tmp_path / "opening.gif", tmp_path / "b.gif"])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()

    assert widget.destination().name == "opening_joined.mp4"
    widget.format_combo.setCurrentText(concat.GIF)
    assert widget.destination().name == "opening_joined.gif"


def test_the_destination_follows_a_chosen_folder(widget, qapp, tmp_path,
                                                 monkeypatch):
    _timeline_of(widget, qapp, tmp_path, monkeypatch)
    out = tmp_path / "elsewhere"
    out.mkdir()
    widget.output_dir = str(out)
    assert widget.destination().parent == out


# ── shutdown ─────────────────────────────────────────────────────────────

def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()


# ── the filmstrip, the preview and the seam finder ───────────────────────

def _moving_gif(path, frames=24, size=(160, 120)):
    """A ball crossing the frame, so one moment is distinguishable from another."""
    from PIL import ImageDraw
    images = []
    for i in range(frames):
        im = Image.new("RGB", size, (20, 20 + i * 4, 60))
        d = ImageDraw.Draw(im)
        x = 8 + (size[0] - 24) * i / (frames - 1)
        d.ellipse([x, size[1] / 2 - 10, x + 16, size[1] / 2 + 6],
                  fill=(240, 190, 60))
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=100, loop=0)
    return path


def _settle(widget, qapp, limit=200):
    """Pump until the background frame loads have finished."""
    for _ in range(limit):
        qapp.processEvents()
        loading = widget._loader is not None and widget._loader.isRunning()
        if not loading and not widget._pending:
            qapp.processEvents()
            return
        if widget._loader is not None:
            widget._loader.wait(200)
    raise AssertionError("frames never finished loading")


def _two_moving(widget, qapp, tmp_path, monkeypatch):
    a = _moving_gif(tmp_path / "a.gif")
    b = _moving_gif(tmp_path / "b.gif")
    _add(widget, qapp, monkeypatch, [a, b])
    widget.library_list.selectAll()
    widget.add_selected_to_timeline()
    _settle(widget, qapp)
    return a, b


def test_the_filmstrip_shows_the_selected_clip(widget, qapp, tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    _settle(widget, qapp)
    assert widget.trim_bar._frames, "the bar never received the clip"
    assert widget.trim_bar._duration > 0


def test_dragging_the_bar_trims_the_segment(widget, qapp, tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    _settle(widget, qapp)

    widget._on_bar_start(0.5)
    assert widget.segments[0].start == pytest.approx(0.5)
    assert widget.segments[0].trimmed
    assert "0.50s" in widget.timeline_list.item(0).text()


def test_the_preview_plays_only_what_is_kept(widget, qapp, tmp_path, monkeypatch):
    """The fallback strip, which is what a build without QtMultimedia flips."""
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    _settle(widget, qapp)

    whole = len(widget._build_play_list())
    widget.segments[0].start = 1.0          # drop the first second of clip one
    trimmed = len(widget._build_play_list())
    assert 0 < trimmed < whole, "trimming did not shorten the preview"


def test_the_fallback_runs_and_stops(widget, qapp, tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget._start_frame_preview()
    _settle(widget, qapp)
    assert widget._playing
    assert widget.preview.pixmap() is not None and not widget.preview.pixmap().isNull()

    widget.stop_preview()
    assert not widget._playing
    assert not widget._play_timer.isActive()


def test_the_fallback_loops_rather_than_ending_on_a_frozen_frame(widget, qapp,
                                                                 tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget._start_frame_preview()
    _settle(widget, qapp)
    widget._play_index = len(widget._play_list) - 1
    widget._advance_playback()
    assert widget._play_index == 0
    widget.stop_preview()


# ── the rendered preview ─────────────────────────────────────────────────

class _FakeWorker:
    """Stands in for the render so the tests exercise the decision, not ffmpeg."""
    last = None

    def __init__(self, segments, destination, options, parent=None):
        _FakeWorker.last = self
        self.segments, self.destination, self.options = segments, destination, options
        self.cancelled = False
        self.progress = _Signal()
        self.done = _Signal()
        self.error = _Signal()
        self.finished = _Signal()

    def cancel(self):
        self.cancelled = True

    def wait(self, _ms=0):
        return True

    def start(self):
        pass


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


def _fake_render(widget, monkeypatch):
    import src.widgets.video_concat_widget as mod
    monkeypatch.setattr(mod, "_JoinWorker", _FakeWorker)
    if widget._player is None:              # a build without QtMultimedia
        widget._player = type("P", (), {"setSource": lambda *a: None,
                                        "play": lambda *a: None,
                                        "stop": lambda *a: None})()
        widget.video = widget.preview


def test_the_preview_is_rendered_small_and_fast(widget, qapp, tmp_path, monkeypatch):
    """A preview that took as long as the export would not be used."""
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    _fake_render(widget, monkeypatch)

    widget.start_preview()
    opts = _FakeWorker.last.options
    assert opts["max_width"] == mod_preview_width()
    assert opts["preset"] == "ultrafast"
    assert opts["crf"] >= 28, "a preview does not need archival quality"
    # and it is the real pipeline, so the framing settings come along
    assert opts["size_mode"] == widget.size_combo.currentText()
    assert opts["background"] == widget._background_value()


def mod_preview_width():
    from src.widgets.video_concat_widget import PREVIEW_WIDTH
    return PREVIEW_WIDTH


def test_an_unchanged_timeline_replays_what_was_already_built(widget, qapp,
                                                              tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    _fake_render(widget, monkeypatch)

    widget.start_preview()
    built = _FakeWorker.last
    fake_file = tmp_path / "preview.mp4"
    fake_file.write_bytes(b"stub")
    built.done.emit(str(fake_file))
    built.finished.emit()
    widget.stop_preview()

    _FakeWorker.last = None
    widget.start_preview()
    assert _FakeWorker.last is None, "an unchanged timeline should not re-render"
    assert widget._playing


def test_changing_a_trim_makes_the_preview_stale(widget, qapp, tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    _fake_render(widget, monkeypatch)

    widget.start_preview()
    fake_file = tmp_path / "preview.mp4"
    fake_file.write_bytes(b"stub")
    _FakeWorker.last.done.emit(str(fake_file))
    _FakeWorker.last.finished.emit()
    widget.stop_preview()

    widget.segments[0].start = 0.5          # the join is now a different join
    _FakeWorker.last = None
    widget.start_preview()
    assert _FakeWorker.last is not None, "a changed timeline must be rebuilt"


def test_one_segment_is_not_a_preview(widget, qapp, tmp_path, monkeypatch):
    a = _moving_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _fake_render(widget, monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    _FakeWorker.last = None
    widget.start_preview()
    assert _FakeWorker.last is None


def test_matching_is_offered_only_where_there_is_something_to_match(widget, qapp,
                                                                    tmp_path, monkeypatch):
    _two_moving(widget, qapp, tmp_path, monkeypatch)
    widget.timeline_list.setCurrentRow(0)
    _settle(widget, qapp)
    assert not widget.match_btn.isEnabled(), "nothing precedes the first segment"

    widget.timeline_list.setCurrentRow(1)
    _settle(widget, qapp)
    assert widget.match_btn.isEnabled()


def test_matching_starts_the_clip_where_the_last_one_left_off(widget, qapp,
                                                              tmp_path, monkeypatch):
    """Both segments are the same footage, so the frame that follows the first
    one's out point is the one at that same time in the second."""
    a = _moving_gif(tmp_path / "a.gif")
    _add(widget, qapp, monkeypatch, [a])
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _select_library(widget, 0)
    widget.add_selected_to_timeline()
    _settle(widget, qapp)

    widget.segments[0].end = 1.2            # first segment stops at 1.2s
    widget.timeline_list.setCurrentRow(1)
    _settle(widget, qapp)

    widget.match_previous()
    _settle(widget, qapp)

    found = widget.segments[1].start
    assert found == pytest.approx(1.2, abs=0.25), \
        f"expected the cut near 1.2s, got {found:.2f}s"
    assert "Matched" in widget.scrub_label.text()
