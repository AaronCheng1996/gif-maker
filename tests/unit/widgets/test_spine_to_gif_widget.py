"""Tests for the Spine to GIF tab, driven against the widget directly."""
import json
from pathlib import Path

import pytest
from PIL import Image

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core.spine import cli_backend
from src.widgets.spine_to_gif_widget import (ENGINE_BUILTIN, ENGINE_CLI, PREVIEW_FPS,
                                              SpineToGifWidget)


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


@pytest.fixture(autouse=True)
def _no_real_cli(monkeypatch):
    """Default every test to the built-in engine; CLI-specific tests opt in."""
    monkeypatch.setattr(cli_backend, "find_cli", lambda *a, **k: None)


@pytest.fixture()
def widget(qapp):
    w = SpineToGifWidget()
    yield w
    # Qt aborts the process if a QThread outlives its widget.
    w.stop_workers()


@pytest.fixture()
def toy_project(tmp_path):
    """A 16x16 red square that slides 16px to the right over 0.4s."""
    page = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    page.paste(Image.new("RGBA", (16, 16), (255, 0, 0, 255)), (0, 0))
    page.save(tmp_path / "sprites.png")
    (tmp_path / "toy.atlas").write_text(
        "sprites.png\nsize: 32, 32\nred\nbounds: 0, 0, 16, 16\n", encoding="utf-8")
    (tmp_path / "toy.json").write_text(json.dumps({
        "skeleton": {"spine": "4.1.23", "x": -32, "y": -32, "width": 64, "height": 64},
        "bones": [{"name": "root"}],
        "slots": [{"name": "s", "bone": "root", "attachment": "red"}],
        "skins": [
            {"name": "default", "attachments": {
                "s": {"red": {"type": "region", "path": "red", "width": 16, "height": 16}}}},
            {"name": "alt", "attachments": {
                "s": {"red": {"type": "region", "path": "red", "width": 16, "height": 16}}}},
        ],
        "animations": {
            "walk": {"bones": {"root": {"translate": [
                {"time": 0, "x": 0, "y": 0}, {"time": 0.4, "x": 16, "y": 0}]}}},
            "idle": {"bones": {"root": {"rotate": [
                {"time": 0, "value": 0}, {"time": 1.0, "value": 45}]}}},
        },
    }), encoding="utf-8")
    return tmp_path / "toy.json"


def _load(widget, path, qapp):
    widget.load_project_file(path)
    assert widget._load_worker.wait(60000)
    qapp.processEvents()


def test_starts_with_no_project(widget):
    assert widget.project is None
    assert widget.export_btn.isEnabled() is False
    assert widget.animation_list.count() == 0
    assert widget.current_animation is None


def test_loads_project_and_lists_animations(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)

    assert widget.project is not None
    assert widget.animation_list.count() == 2
    labels = [widget.animation_list.item(i).text() for i in range(2)]
    assert any("walk" in t for t in labels)
    assert any("idle" in t for t in labels)
    # The label carries duration and an fps-derived frame estimate.
    walk_label = next(t for t in labels if "walk" in t)
    assert "0.40s" in walk_label
    assert "frames" in walk_label


def test_load_populates_skins_and_enables_export(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    assert [widget.skin_combo.itemText(i) for i in range(widget.skin_combo.count())] == \
        ["default", "alt"]
    assert widget.export_btn.isEnabled() is True


def test_project_label_reports_skeleton_stats(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    text = widget.project_label.text()
    assert "toy" in text
    assert "4.1.23" in text
    assert "1 bones" in text and "1 slots" in text


def test_selecting_animation_sets_up_the_scrubber(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    qapp.processEvents()
    assert widget.current_animation is not None
    assert widget.time_slider.maximum() > 0
    assert "/" in widget.time_label.text()


def test_scrubbing_updates_the_time_label(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    row = next(i for i in range(2)
               if widget.animation_list.item(i).data(256) == "idle")
    widget.animation_list.setCurrentRow(row)
    qapp.processEvents()
    widget.time_slider.setValue(widget.time_slider.maximum())
    assert widget.time_label.text().startswith("1.00s")


def test_load_failure_is_reported(widget, tmp_path, qapp):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    widget.load_project_file(tmp_path / "bad.json")
    assert widget._load_worker.wait(60000)
    qapp.processEvents()
    assert widget.project is None
    assert widget.export_btn.isEnabled() is False


def test_preview_renders_a_frame(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    qapp.processEvents()
    widget._render_preview()
    assert widget._preview_worker.wait(60000)
    qapp.processEvents()
    pixmap = widget.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_playback_toggles(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    qapp.processEvents()
    widget.toggle_playback()
    assert widget._playing is True
    assert widget.play_btn.text() == "⏸"
    widget.toggle_playback()
    assert widget._playing is False
    assert widget.play_btn.text() == "▶"


def test_fps_change_rescales_frame_estimate(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    qapp.processEvents()
    widget.fps_spinbox.setValue(10)
    low = widget.time_slider.maximum()
    widget.fps_spinbox.setValue(30)
    assert widget.time_slider.maximum() > low


def test_scale_change_updates_output_size_label(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    qapp.processEvents()
    widget.scale_spinbox.setValue(1.0)
    assert "64×64" in widget.size_label.text()
    widget.scale_spinbox.setValue(0.5)
    assert "32×32" in widget.size_label.text()


def test_exports_a_gif_with_the_expected_frame_count(widget, toy_project, qapp, tmp_path,
                                                     monkeypatch):
    _load(widget, toy_project, qapp)
    row = next(i for i in range(2)
               if widget.animation_list.item(i).data(256) == "walk")
    widget.animation_list.setCurrentRow(row)
    qapp.processEvents()

    out = tmp_path / "out.gif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    widget.fps_spinbox.setValue(10)
    widget.scale_spinbox.setValue(1.0)
    widget.export_gif()
    assert widget._export_worker.wait(120000)
    qapp.processEvents()

    assert out.exists()
    img = Image.open(out)
    try:
        assert getattr(img, "n_frames", 1) == 4   # 0.4s at 10 fps
        assert img.size == (64, 64)
    finally:
        img.close()


def test_export_without_a_project_does_nothing(widget, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: called.append(1) or ("", ""))
    widget.export_gif()
    assert not called


def test_crop_to_animation_changes_output_size(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    row = next(i for i in range(2)
               if widget.animation_list.item(i).data(256) == "walk")
    widget.animation_list.setCurrentRow(row)
    qapp.processEvents()
    widget.scale_spinbox.setValue(1.0)
    full = widget.size_label.text()

    widget.tight_bounds_checkbox.setChecked(True)
    qapp.processEvents()
    cropped = widget.size_label.text()
    # The sprite only spans 32x16 of the 64x64 export bounding box.
    assert cropped != full
    assert "32×16" in cropped


def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()


# ── engine selection ─────────────────────────────────────────────────────

def test_falls_back_to_builtin_when_cli_is_absent(widget):
    assert widget.cli_path is None
    assert widget.engine == ENGINE_BUILTIN
    assert "not found" in widget.engine_status.text()


def test_prefers_the_cli_when_present(qapp, monkeypatch, tmp_path):
    fake = tmp_path / cli_backend.EXE_NAME
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli_backend, "find_cli", lambda *a, **k: str(fake))
    w = SpineToGifWidget()
    try:
        assert w.engine == ENGINE_CLI
        assert str(fake) in w.engine_status.text()
        # Palette size is the built-in encoder's knob; the CLI does its own.
        assert w.colors_combo.isEnabled() is False
        assert w.format_combo.isEnabled() is True
    finally:
        w.stop_workers()


def test_switching_to_builtin_reenables_its_own_options(qapp, monkeypatch, tmp_path):
    fake = tmp_path / cli_backend.EXE_NAME
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli_backend, "find_cli", lambda *a, **k: str(fake))
    w = SpineToGifWidget()
    try:
        w.engine_combo.setCurrentText(ENGINE_BUILTIN)
        assert w.colors_combo.isEnabled() is True
        assert w.tight_bounds_checkbox.isEnabled() is True
        assert w.format_combo.isEnabled() is False
    finally:
        w.stop_workers()


def test_extension_follows_the_selected_cli_format(qapp, monkeypatch, tmp_path):
    fake = tmp_path / cli_backend.EXE_NAME
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli_backend, "find_cli", lambda *a, **k: str(fake))
    w = SpineToGifWidget()
    try:
        w.format_combo.setCurrentText("Gif")
        assert w._extension_for_format() == "gif"
        w.format_combo.setCurrentText("Mp4")
        assert w._extension_for_format() == "mp4"
        w.format_combo.setCurrentText("Apng")
        assert w._extension_for_format() == "png"
        # The built-in engine always writes GIF.
        w.engine_combo.setCurrentText(ENGINE_BUILTIN)
        assert w._extension_for_format() == "gif"
    finally:
        w.stop_workers()


# ── multi-select / batch ─────────────────────────────────────────────────

def test_select_all_selects_every_animation(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.select_all_animations()
    assert sorted(widget.selected_animations()) == ["idle", "walk"]


def test_selected_animations_falls_back_to_the_current_row(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    widget.animation_list.clearSelection()
    assert len(widget.selected_animations()) == 1


def test_export_button_reflects_the_selection_count(widget, toy_project, qapp):
    _load(widget, toy_project, qapp)
    widget.animation_list.setCurrentRow(0)
    widget.animation_list.clearSelection()
    widget.animation_list.item(0).setSelected(True)
    qapp.processEvents()
    assert "2 animations" not in widget.export_btn.text()

    widget.select_all_animations()
    qapp.processEvents()
    assert "2 animations" in widget.export_btn.text()


def test_batch_export_writes_one_file_per_animation(widget, toy_project, qapp, tmp_path,
                                                    monkeypatch):
    _load(widget, toy_project, qapp)
    widget.select_all_animations()
    qapp.processEvents()

    outdir = tmp_path / "batch"
    outdir.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(outdir))
    widget.fps_spinbox.setValue(6)
    widget.scale_spinbox.setValue(0.5)
    widget.export_gif()
    assert widget._export_worker.wait(300000)
    qapp.processEvents()

    produced = sorted(p.name for p in outdir.glob("*.gif"))
    assert produced == ["toy_idle.gif", "toy_walk.gif"]


def test_batch_filenames_are_sanitised(widget, tmp_path, qapp, monkeypatch):
    """Animation names with path-hostile characters still produce valid files."""
    import json

    from PIL import Image
    page = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    page.paste(Image.new("RGBA", (16, 16), (255, 0, 0, 255)), (0, 0))
    page.save(tmp_path / "sprites.png")
    (tmp_path / "m.atlas").write_text(
        "sprites.png\nsize: 32, 32\nred\nbounds: 0, 0, 16, 16\n", encoding="utf-8")
    (tmp_path / "m.json").write_text(json.dumps({
        "skeleton": {"spine": "4.1.23", "x": -32, "y": -32, "width": 64, "height": 64},
        "bones": [{"name": "root"}],
        "slots": [{"name": "s", "bone": "root", "attachment": "red"}],
        "skins": [{"name": "default", "attachments": {
            "s": {"red": {"type": "region", "path": "red", "width": 16, "height": 16}}}}],
        "animations": {
            "a/b": {"bones": {"root": {"rotate": [
                {"time": 0, "value": 0}, {"time": 0.2, "value": 10}]}}},
            "c:d": {"bones": {"root": {"rotate": [
                {"time": 0, "value": 0}, {"time": 0.2, "value": 10}]}}},
        },
    }), encoding="utf-8")

    _load(widget, tmp_path / "m.json", qapp)
    widget.select_all_animations()
    qapp.processEvents()

    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(outdir))
    widget.fps_spinbox.setValue(5)
    widget.scale_spinbox.setValue(0.5)
    widget.export_gif()
    assert widget._export_worker.wait(300000)
    qapp.processEvents()

    files = sorted(p.name for p in outdir.glob("*.gif"))
    assert len(files) == 2
    assert all("/" not in f and ":" not in f for f in files)


def test_cancelled_directory_dialog_aborts_batch(widget, toy_project, qapp, monkeypatch):
    _load(widget, toy_project, qapp)
    widget.select_all_animations()
    qapp.processEvents()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    widget.export_gif()
    assert widget._export_worker is None or not widget._export_worker.isRunning()


# ── CLI preview: render the animation once, then scrub it from disk ──────

@pytest.fixture()
def fake_render(monkeypatch):
    """Replace the CLI render with one that writes frames straight to disk."""
    calls = []

    def install(frames=3, error=None):
        def render(skeleton_path, output_dir, animation, options=None, cli_path=None,
                   atlas_path=None, on_frame=None, should_stop=None, **kwargs):
            calls.append((animation, options))
            if error is not None:
                raise error
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            written = []
            for i in range(frames):
                path = output_dir / f"frame_{i:06d}.png"
                Image.new("RGBA", (8, 8), (10 * i, 0, 0, 255)).save(path)
                written.append(path)
                if on_frame is not None:
                    on_frame(i, path)
            return written

        monkeypatch.setattr(cli_backend, "render_frame_sequence", render)
        return calls

    return install


@pytest.fixture()
def cli_widget(qapp, monkeypatch, tmp_path):
    fake = tmp_path / cli_backend.EXE_NAME
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli_backend, "find_cli", lambda *a, **k: str(fake))
    w = SpineToGifWidget()
    yield w
    w.stop_workers()
    w._discard_preview_frames()


def _select(widget, qapp, row=0):
    widget.animation_list.setCurrentRow(row)
    qapp.processEvents()
    worker = widget._cli_preview_worker
    if worker is not None:
        assert worker.wait(60000)
    qapp.processEvents()


def test_cli_engine_previews_from_rendered_frames(cli_widget, toy_project, qapp, fake_render):
    calls = fake_render(frames=4)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    assert len(calls) == 1
    assert len(cli_widget._frame_paths) == 4
    # One slider notch per frame, so scrubbing lands on frames the CLI produced.
    assert cli_widget.time_slider.maximum() == 3
    pixmap = cli_widget.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_scrubbing_rendered_frames_does_not_re_render(cli_widget, toy_project, qapp,
                                                      fake_render):
    calls = fake_render(frames=4)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    for value in (3, 1, 2, 0):
        cli_widget.time_slider.setValue(value)
        qapp.processEvents()
    assert len(calls) == 1


def test_returning_to_an_animation_reuses_its_frames(cli_widget, toy_project, qapp,
                                                     fake_render):
    calls = fake_render(frames=4)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp, row=0)
    _select(cli_widget, qapp, row=1)
    _select(cli_widget, qapp, row=0)

    # Two animations, two renders — the third selection came off the disk cache.
    assert len(calls) == 2
    assert len(cli_widget._frame_paths) == 4


def test_changing_the_skin_re_renders(cli_widget, toy_project, qapp, fake_render):
    calls = fake_render(frames=2)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.skin_combo.setCurrentText("alt")
    qapp.processEvents()
    if cli_widget._cli_preview_worker is not None:
        assert cli_widget._cli_preview_worker.wait(60000)
    qapp.processEvents()
    assert len(calls) == 2


def test_export_only_settings_do_not_discard_the_preview(cli_widget, toy_project, qapp,
                                                         fake_render):
    calls = fake_render(frames=2)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    # fps, scale and loop change the file, not what the animation looks like.
    cli_widget.fps_spinbox.setValue(30)
    cli_widget.scale_spinbox.setValue(0.5)
    cli_widget.loop_spinbox.setValue(3)
    cli_widget.time_slider.setValue(1)
    qapp.processEvents()
    assert len(calls) == 1


def test_rendered_frames_play_back_at_the_preview_rate(cli_widget, toy_project, qapp,
                                                       fake_render):
    fake_render(frames=4)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.fps_spinbox.setValue(30)   # export fps, not the preview's
    cli_widget.play_playback()
    try:
        assert cli_widget._play_timer.interval() == int(1000 / PREVIEW_FPS)
    finally:
        cli_widget.pause_playback()


def test_preview_falls_back_to_the_builtin_renderer_when_the_cli_fails(
        cli_widget, toy_project, qapp, fake_render):
    fake_render(error=RuntimeError("no runtime for this model"))
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    assert cli_widget._frame_paths == []
    assert "built-in" in cli_widget.preview_status.text()
    assert "no runtime for this model" in cli_widget.preview_status.text()


def test_switching_to_the_builtin_engine_stops_using_rendered_frames(
        cli_widget, toy_project, qapp, fake_render):
    fake_render(frames=4)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)
    assert cli_widget._frame_paths

    cli_widget.engine_combo.setCurrentText(ENGINE_BUILTIN)
    qapp.processEvents()
    assert cli_widget._frame_paths == []
    assert cli_widget._frame_key is None


def test_discarding_frames_removes_the_temp_folder(cli_widget, toy_project, qapp,
                                                   fake_render):
    fake_render(frames=2)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    root = cli_widget._frames_root
    assert root is not None and root.exists()
    cli_widget._discard_preview_frames()
    assert not root.exists()
    assert cli_widget._frames_root is None


# ── still export: Png/Jpg take the frame the preview is showing ──────────

@pytest.fixture()
def recorded_export(monkeypatch):
    """Capture the ExportOptions the CLI would have been driven with."""
    calls = []

    def fake_export(skeleton_path, output_path, animations, options=None, **kwargs):
        calls.append({"animations": list(animations), "options": options,
                      "output": str(output_path)})
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"stub")
        return str(output_path)

    monkeypatch.setattr(cli_backend, "export_animation", fake_export)
    return calls


def _export_one(widget, qapp, monkeypatch, out_path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out_path), ""))
    widget.export_gif()
    assert widget._export_worker.wait(120000)
    qapp.processEvents()


def test_still_export_uses_the_scrubbed_time(cli_widget, toy_project, qapp, tmp_path,
                                             monkeypatch, fake_render, recorded_export):
    fake_render(frames=5)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.format_combo.setCurrentText("Png")
    cli_widget.time_slider.setValue(cli_widget.time_slider.maximum())
    qapp.processEvents()
    expected = cli_widget._current_time()
    assert expected > 0

    _export_one(cli_widget, qapp, monkeypatch, tmp_path / "still.png")
    assert len(recorded_export) == 1
    assert recorded_export[0]["options"].start_time == pytest.approx(expected)


def test_animated_export_ignores_the_scrubbed_time(cli_widget, toy_project, qapp, tmp_path,
                                                   monkeypatch, fake_render, recorded_export):
    fake_render(frames=5)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.format_combo.setCurrentText("Gif")
    cli_widget.time_slider.setValue(cli_widget.time_slider.maximum())
    qapp.processEvents()

    _export_one(cli_widget, qapp, monkeypatch, tmp_path / "out.gif")
    # A GIF is the whole animation, so it always starts at the beginning.
    assert recorded_export[0]["options"].start_time == 0.0


def test_still_formats_report_a_frame_not_a_frame_count(cli_widget, toy_project, qapp,
                                                        fake_render):
    fake_render(frames=5)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.format_combo.setCurrentText("Jpg")
    qapp.processEvents()
    assert cli_widget._exports_a_still() is True
    assert "One still frame" in cli_widget.estimate_label.text()

    cli_widget.format_combo.setCurrentText("Gif")
    qapp.processEvents()
    assert cli_widget._exports_a_still() is False
    assert "frames at" in cli_widget.estimate_label.text()


def test_jpg_maps_to_a_jpg_extension(cli_widget):
    cli_widget.format_combo.setCurrentText("Jpg")
    assert cli_widget._extension_for_format() == "jpg"


def test_batch_of_stills_is_named_as_such(cli_widget, toy_project, qapp, fake_render):
    fake_render(frames=3)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)

    cli_widget.format_combo.setCurrentText("Png")
    cli_widget.select_all_animations()
    qapp.processEvents()
    assert "2 stills" in cli_widget.export_btn.text()

    cli_widget.format_combo.setCurrentText("Gif")
    qapp.processEvents()
    assert "2 animations" in cli_widget.export_btn.text()


def test_changing_fps_keeps_one_slider_notch_per_rendered_frame(cli_widget, toy_project,
                                                                qapp, fake_render):
    fake_render(frames=6)
    _load(cli_widget, toy_project, qapp)
    _select(cli_widget, qapp)
    assert cli_widget.time_slider.maximum() == 5

    # The fps-derived estimate must not resize a slider that is indexing frames
    # the CLI has already written to disk.
    cli_widget.fps_spinbox.setValue(60)
    qapp.processEvents()
    assert cli_widget.time_slider.maximum() == 5


def test_default_skin_wins_over_the_order_the_cli_lists(widget, qapp, tmp_path):
    class Info:
        # The order SpineViewerCLI actually reports for a costume-variant model.
        skins = ["AVG", "CoverUpMode_01/3", "default", "CoverUpMode_02/1", "1"]
        animations = {"Idle": 8.0}
        slots = []

    widget.skeleton_path = tmp_path / "m.json"
    widget._on_project_loaded(None, Info(), "")
    qapp.processEvents()
    assert widget.skin_combo.currentText() == "default"


def test_first_skin_is_kept_when_there_is_no_default(widget, qapp, tmp_path):
    class Info:
        skins = ["outfit_a", "outfit_b"]
        animations = {"Idle": 8.0}
        slots = []

    widget.skeleton_path = tmp_path / "m.json"
    widget._on_project_loaded(None, Info(), "")
    qapp.processEvents()
    assert widget.skin_combo.currentText() == "outfit_a"

