"""The packaged app must never flash a console window.

Run from source there is a console for children to inherit and nothing shows, so
this is invisible in development and only appears in the built exe — which is
exactly why it needs a test rather than a look.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

from src.core import proc as proc_mod
from src.core.proc import CREATE_NO_WINDOW, popen_hidden, run_hidden

SRC = Path(__file__).resolve().parents[3] / "src"
LAUNCHERS = {"run", "Popen", "call", "check_call", "check_output"}


def _recorder(store):
    def fake(cmd, **kwargs):
        store.append((cmd, kwargs))
        return "sentinel"
    return fake


@pytest.mark.skipif(sys.platform != "win32", reason="the flag is Windows-only")
def test_the_no_window_flag_goes_out_with_every_run(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _recorder(calls))
    run_hidden(["ffmpeg", "-version"], capture_output=True)
    _cmd, kwargs = calls[0]
    assert kwargs["creationflags"] == CREATE_NO_WINDOW
    assert kwargs["capture_output"] is True, "the caller's own arguments survive"


@pytest.mark.skipif(sys.platform != "win32", reason="the flag is Windows-only")
def test_the_no_window_flag_goes_out_with_every_popen(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", _recorder(calls))
    popen_hidden(["ffmpeg"], stdout=subprocess.PIPE)
    assert calls[0][1]["creationflags"] == CREATE_NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason="the flag is Windows-only")
def test_a_caller_that_asks_for_other_flags_keeps_them(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _recorder(calls))
    run_hidden(["x"], creationflags=0x00000200)
    assert calls[0][1]["creationflags"] == 0x00000200


def test_no_flag_is_passed_where_the_platform_rejects_it(monkeypatch):
    """creationflags is not a POSIX argument, so it must not be sent there."""
    monkeypatch.setattr(sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(subprocess, "run", _recorder(calls))
    proc_mod.run_hidden(["ls"])
    assert "creationflags" not in calls[0][1]


def _plain_launches(path: Path):
    """subprocess.run / Popen / … called directly, which would flash a window."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and fn.attr in LAUNCHERS
                and isinstance(fn.value, ast.Name) and fn.value.id == "subprocess"):
            found.append(f"{path.name}:{node.lineno} subprocess.{fn.attr}")
    return found


def test_nothing_launches_a_process_the_plain_way():
    """One missed call site is still a visible flash, so none are allowed.

    Use run_hidden / popen_hidden from src.core.proc instead."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "proc.py":
            continue                      # the one place allowed to call it
        offenders += _plain_launches(path)
    assert offenders == [], (
        "these bypass src/core/proc.py and will flash a console in the exe: "
        + ", ".join(offenders))
