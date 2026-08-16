"""Unit tests for the SpineViewerCLI backend wrapper (no real CLI needed)."""
import io
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from src.core.spine import cli_backend as cb

QUERY_OUTPUT = """>>>>>>>>>>>>>>> Skins >>>>>>>>>>>>>>>
Name
default
skin1
skin2
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
>>>>>>>>>>>>>>> Animations >>>>>>>>>>>>>>>
Name\tDuration
act1\t2
act2\t1.2
act3\t0.6667
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
>>>>>>>>>>>>>>> Slots >>>>>>>>>>>>>>>
Name\tAttachments
head\thead
armL\tarmL skin12;armL skin34
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
"""


def test_parses_skins_animations_and_slots():
    info = cb.parse_query_output(QUERY_OUTPUT)
    assert info.skins == ["default", "skin1", "skin2"]
    assert info.animations == {"act1": 2.0, "act2": 1.2, "act3": 0.6667}
    assert info.slots == ["head", "armL"]


def test_query_skips_table_headers():
    info = cb.parse_query_output(QUERY_OUTPUT)
    assert "Name" not in info.skins
    assert "Name" not in info.animations


def test_parses_empty_output():
    info = cb.parse_query_output("")
    assert info.skins == [] and info.animations == {} and info.slots == []


def test_animation_with_unparseable_duration_defaults_to_zero():
    out = (">>>>>>> Animations >>>>>>>\nName\tDuration\nweird\tabc\n<<<<<<<\n")
    info = cb.parse_query_output(out)
    assert info.animations == {"weird": 0.0}


# ── ExportOptions ────────────────────────────────────────────────────────

def test_export_options_defaults_include_required_flags():
    args = cb.ExportOptions().to_args()
    assert "-f" in args and "Gif" in args
    assert "--fps" in args and "--scale" in args


def test_loop_flag_only_present_when_enabled():
    assert "--loop" in cb.ExportOptions(loop=True).to_args()
    assert "--loop" not in cb.ExportOptions(loop=False).to_args()


def test_skins_are_passed_individually():
    args = cb.ExportOptions(skins=["a", "b"]).to_args()
    assert args.count("--skins") == 2
    assert "a" in args and "b" in args


def test_background_colour_is_only_sent_when_set():
    assert "--color" not in cb.ExportOptions(background=None).to_args()
    args = cb.ExportOptions(background="#FFFFFFFF").to_args()
    assert "--color" in args and "#FFFFFFFF" in args


def test_pma_and_drop_last_frame_flags():
    args = cb.ExportOptions(pma=True, drop_last_frame=True).to_args()
    assert "--pma" in args and "--drop-last-frame" in args
    plain = cb.ExportOptions().to_args()
    assert "--pma" not in plain and "--drop-last-frame" not in plain


def test_format_and_numeric_options_round_trip():
    args = cb.ExportOptions(fmt="Mp4", fps=60, scale=0.5, margin=10,
                            max_resolution=1024, start_time=1.5,
                            duration=2.0, speed=2.0).to_args()
    pairs = dict(zip(args, args[1:]))
    assert pairs["-f"] == "Mp4"
    assert pairs["--fps"] == "60"
    assert pairs["--scale"] == "0.5"
    assert pairs["--margin"] == "10"
    assert pairs["--max-resolution"] == "1024"
    assert pairs["--time"] == "1.5"
    assert pairs["--duration"] == "2.0"
    assert pairs["--speed"] == "2.0"


# ── discovery ────────────────────────────────────────────────────────────

def test_find_cli_honours_environment_variable(tmp_path, monkeypatch):
    fake = tmp_path / cb.EXE_NAME
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("SPINEVIEWER_CLI", str(fake))
    assert cb.find_cli() == str(fake)
    assert cb.is_available() is True


def test_find_cli_ignores_environment_variable_pointing_nowhere(tmp_path, monkeypatch):
    monkeypatch.setenv("SPINEVIEWER_CLI", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(cb.shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(cb, "_COMMON_DIRS", [])
    assert cb.find_cli() is None


def test_find_cli_searches_extra_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("SPINEVIEWER_CLI", raising=False)
    monkeypatch.setattr(cb.shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(cb, "_COMMON_DIRS", [])
    exe = tmp_path / cb.EXE_NAME
    exe.write_text("", encoding="utf-8")
    assert cb.find_cli(extra_dirs=[tmp_path]) == str(exe)


def test_find_cli_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("SPINEVIEWER_CLI", raising=False)
    monkeypatch.setattr(cb.shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(cb, "_COMMON_DIRS", [])
    assert cb.find_cli(extra_dirs=[tmp_path]) is None
    assert cb.is_available() is False


def test_export_requires_a_located_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "find_cli", lambda *_a, **_k: None)
    with pytest.raises(cb.SpineCliError):
        cb.export_animation(tmp_path / "a.json", tmp_path / "o.gif", ["x"])


def test_export_requires_at_least_one_animation(tmp_path):
    with pytest.raises(cb.SpineCliError):
        cb.export_animation(tmp_path / "a.json", tmp_path / "o.gif", [],
                            cli_path=str(tmp_path / cb.EXE_NAME))


def test_install_hint_points_at_the_release_page():
    hint = cb.get_install_hint()
    assert "github.com/ww-rm/SpineViewer" in hint


def test_gif_is_the_first_offered_format():
    assert cb.EXPORT_FORMATS[0] == "Gif"


# ── framing ──────────────────────────────────────────────────────────────

def test_framing_reports_canvas_in_skeleton_units():
    f = cb.Framing(100, 50, (10, 5, 90, 45), scale=0.25)
    assert f.canvas_size_units() == (400.0, 200.0)


def test_framing_to_bounds_aligns_the_canvas_with_the_content():
    """The probe's content position pins the canvas down in skeleton space."""
    # Canvas 400x200 units. Content starts 10px/0.25 = 40 units from the left,
    # and 5px/0.25 = 20 units below the top.
    f = cb.Framing(100, 50, (10, 5, 90, 45), scale=0.25)
    # Built-in render says that content occupies x 0..320, y 0..160.
    x, y, w, h = cb.framing_to_bounds(f, (0.0, 0.0, 320.0, 160.0))
    assert (w, h) == (400.0, 200.0)
    assert x == -40.0                 # canvas starts 40 units left of the content
    # Canvas top is 20 units above the content top (160), so the bottom is at
    # 180 - 200 = -20.
    assert y == pytest.approx(-20.0)


def test_framing_to_bounds_centres_when_nothing_is_visible():
    f = cb.Framing(100, 50, None, scale=0.5)
    x, y, w, h = cb.framing_to_bounds(f, (0.0, 0.0, 100.0, 100.0))
    assert (w, h) == (200.0, 100.0)
    assert x == pytest.approx(50.0 - 100.0)
    assert y == pytest.approx(50.0 - 50.0)


def test_probe_falls_back_to_gif_for_video_formats(monkeypatch, tmp_path):
    """Video probes cannot be measured with Pillow, so they use a GIF instead."""
    seen = {}

    def fake_export(skeleton, output, animations, options=None, **kwargs):
        seen["fmt"] = options.fmt
        from PIL import Image
        Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(output)
        return str(output)

    monkeypatch.setattr(cb, "export_animation", fake_export)
    monkeypatch.setattr(cb, "find_cli", lambda *a, **k: "cli")
    cb.probe_framing(tmp_path / "m.json", "walk", fmt="Mp4", scale=0.5)
    assert seen["fmt"] == "Gif"


def test_probe_measures_canvas_and_content(monkeypatch, tmp_path):
    def fake_export(skeleton, output, animations, options=None, **kwargs):
        from PIL import Image
        img = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (6, 4), (255, 0, 0, 255)), (5, 3))
        img.save(output)
        return str(output)

    monkeypatch.setattr(cb, "export_animation", fake_export)
    monkeypatch.setattr(cb, "find_cli", lambda *a, **k: "cli")
    f = cb.probe_framing(tmp_path / "m.json", "walk", scale=0.5)
    assert (f.canvas_w_px, f.canvas_h_px) == (20, 10)
    assert f.content_box_px == (5, 3, 11, 7)
    assert f.canvas_size_units() == (40.0, 20.0)


# ── render_frame_sequence: streaming a preview out of the CLI ────────────

class _FakeProc:
    """A stand-in for a running SpineViewerCLI that drips frames onto disk."""

    def __init__(self, out_dir, frames, returncode, delay, log):
        self.out_dir = Path(out_dir)
        self.frames = frames
        self.stdout = io.StringIO(log)
        self.returncode = None
        self.terminated = False
        self._final = returncode
        self._delay = delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._write, daemon=True)
        self._thread.start()

    def _write(self):
        for i in range(self.frames):
            if self._stop.is_set():
                break
            time.sleep(self._delay)
            Image.new("RGBA", (4, 4), (i, 0, 0, 255)).save(
                self.out_dir / f"frame_15_{i:06d}.png")
        self.returncode = self._final

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self._thread.join(timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self._stop.set()
        self._thread.join(5)

    kill = terminate


class _FakeCli:
    def __init__(self, frames, returncode=0, delay=0.01, log=""):
        self._args = (frames, returncode, delay, log)
        self.cmd = []
        self.proc = None

    def __call__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        self.proc = _FakeProc(out_dir, *self._args)
        return self.proc


@pytest.fixture()
def fake_cli(monkeypatch):
    def install(**kwargs):
        cli = _FakeCli(**kwargs)
        monkeypatch.setattr(cb.subprocess, "Popen", cli)
        return cli
    return install


def test_frame_sequence_reports_every_frame_in_order(fake_cli, tmp_path):
    cli = fake_cli(frames=5)
    seen = []
    frames = cb.render_frame_sequence(
        tmp_path / "m.json", tmp_path / "out", "walk", cli_path="cli",
        on_frame=lambda i, p: seen.append((i, p)), poll_interval=0.005)

    assert len(frames) == 5
    assert [i for i, _ in seen] == [0, 1, 2, 3, 4]
    # The last file is held back while the CLI runs, so it can only be reported
    # once the process has exited — but it must still be reported.
    assert [p for _, p in seen] == frames
    assert all(p.exists() for p in frames)


def test_frame_sequence_only_reports_complete_files(fake_cli, tmp_path):
    fake_cli(frames=6)
    decoded = []
    cb.render_frame_sequence(
        tmp_path / "m.json", tmp_path / "out", "walk", cli_path="cli",
        on_frame=lambda i, p: decoded.append(Image.open(p).size), poll_interval=0.005)
    assert decoded == [(4, 4)] * 6


def test_frame_sequence_forces_the_frames_format(fake_cli, tmp_path):
    cli = fake_cli(frames=1)
    options = cb.ExportOptions(fmt="Gif", fps=15)
    cb.render_frame_sequence(tmp_path / "m.json", tmp_path / "out", "walk",
                             options=options, cli_path="cli", poll_interval=0.005)

    assert cli.cmd[cli.cmd.index("-f") + 1] == "Frames"
    assert cli.cmd[cli.cmd.index("-a") + 1] == "walk"
    # The caller's options are left alone.
    assert options.fmt == "Gif"


def test_frame_sequence_stops_when_asked(fake_cli, tmp_path):
    cli = fake_cli(frames=100, delay=0.01)
    stop = {"now": False}

    def on_frame(index, _path):
        if index >= 1:
            stop["now"] = True

    frames = cb.render_frame_sequence(
        tmp_path / "m.json", tmp_path / "out", "walk", cli_path="cli",
        on_frame=on_frame, should_stop=lambda: stop["now"], poll_interval=0.005)

    assert 0 < len(frames) < 100
    assert cli.proc.terminated is True


def test_frame_sequence_reports_a_failing_cli(fake_cli, tmp_path):
    fake_cli(frames=1, returncode=3, log="boom: bad skeleton\n")
    with pytest.raises(cb.SpineCliError) as excinfo:
        cb.render_frame_sequence(tmp_path / "m.json", tmp_path / "out", "walk",
                                 cli_path="cli", poll_interval=0.005)
    assert "code 3" in str(excinfo.value)
    assert "bad skeleton" in str(excinfo.value)


def test_frame_sequence_requires_a_located_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "find_cli", lambda *a, **k: None)
    with pytest.raises(cb.SpineCliError):
        cb.render_frame_sequence(tmp_path / "m.json", tmp_path / "out", "walk")


def test_jpg_is_an_offered_format():
    assert "Jpg" in cb.EXPORT_FORMATS
    assert cb.PROBE_EXTENSIONS["Jpg"] == "jpg"


def test_still_formats_are_the_single_frame_ones():
    assert cb.STILL_FORMATS == {"Png", "Jpg"}
    assert not (cb.STILL_FORMATS & {"Gif", "Apng", "Webpa", "Frames", "Mp4"})


def test_start_time_reaches_the_command_line():
    args = cb.ExportOptions(fmt="Png", start_time=3.25).to_args()
    assert args[args.index("--time") + 1] == "3.25"
