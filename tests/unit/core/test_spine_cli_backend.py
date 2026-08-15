"""Unit tests for the SpineViewerCLI backend wrapper (no real CLI needed)."""
import sys
from pathlib import Path

import pytest

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
