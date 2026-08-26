"""Launching child processes without a console window flashing up.

Run from source there is already a console for children to inherit, so nothing
shows. A packaged windowed build has none, and Windows then gives every child a
brand new console: a black window that pops up and vanishes for each ffmpeg,
ffprobe or gifsicle call. It is worst where a tool probes a file just to show it
— picking a video in the Crop tab reads its dimensions and decodes preview
frames, so the flashing happens per click rather than per export.

CREATE_NO_WINDOW suppresses it, and it only works if every call site passes it:
one plain subprocess call is still a visible flash. Hence this module — the
place to add the flag once instead of remembering it eleven times.
"""
import subprocess
import sys

# Windows-only; the flag is not accepted on other platforms, so it is added
# there and nowhere else rather than passed as a zero.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _hidden(kwargs: dict) -> dict:
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return kwargs


def run_hidden(cmd, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run, with no console window in a packaged build."""
    return subprocess.run(cmd, **_hidden(kwargs))


def popen_hidden(cmd, **kwargs) -> subprocess.Popen:
    """subprocess.Popen, with no console window in a packaged build."""
    return subprocess.Popen(cmd, **_hidden(kwargs))
