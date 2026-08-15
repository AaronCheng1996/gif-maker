"""Drive SpineViewerCLI.exe as an export backend.

SpineViewerCLI (https://github.com/ww-rm/SpineViewer) bundles the official Spine
runtimes (2.1 through 4.2) plus its own ffmpeg, and can export straight to GIF —
so when it is available it renders more accurately and covers far more Spine
versions than the built-in Python runtime, and needs no intermediate MP4.

This module only shells out to it; nothing here imports PyQt6.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

EXE_NAME = "SpineViewerCLI.exe" if sys.platform == "win32" else "SpineViewerCLI"

# Formats the CLI accepts for -f. GIF is what this app cares about, but the
# others are handy for users who want a lossless master alongside the GIF.
EXPORT_FORMATS = ["Gif", "Apng", "Webp", "Webpa", "Png", "Frames", "Mp4", "Mov", "Webm", "Mkv"]

# Where SpineViewer commonly ends up when unpacked by hand.
_COMMON_DIRS = [
    Path.home() / "AppData" / "Local" / "SpineViewer",
    Path.home() / "Downloads" / "SpineViewer",
    Path.home() / "Desktop" / "SpineViewer",
    Path("C:/Program Files/SpineViewer"),
    Path("C:/Program Files (x86)/SpineViewer"),
]

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class SpineCliError(Exception):
    pass


class ModelInfo:
    """What `SpineViewerCLI query` reports about a model."""

    def __init__(self, skins: List[str], animations: Dict[str, float], slots: List[str]):
        self.skins = skins
        self.animations = animations  # name -> duration in seconds
        self.slots = slots


def _configured_path() -> Optional[str]:
    """An explicit path set by the user (via settings or environment)."""
    env = os.environ.get("SPINEVIEWER_CLI")
    if env and Path(env).exists():
        return env
    try:
        from ... import settings as app_settings  # type: ignore
        configured = app_settings.get("spineviewer_cli_path", "")
        if configured and Path(configured).exists():
            return configured
    except Exception:
        pass
    return None


def find_cli(extra_dirs: Optional[List[Path]] = None) -> Optional[str]:
    """Locate SpineViewerCLI, or return None.

    Order: explicit setting/env var, PATH, then a few well-known folders."""
    configured = _configured_path()
    if configured:
        return configured

    found = shutil.which(EXE_NAME)
    if found:
        return found

    candidates = list(extra_dirs or []) + _COMMON_DIRS
    for directory in candidates:
        try:
            exe = Path(directory) / EXE_NAME
            if exe.exists():
                return str(exe)
        except (OSError, ValueError):
            continue
    return None


def is_available() -> bool:
    return find_cli() is not None


def _run(args: List[str], cli_path: str, timeout: Optional[int] = None,
         on_line: Optional[Callable[[str], None]] = None) -> str:
    """Run the CLI and return its combined output.

    The CLI logs to stderr even on success, so output is merged and the exit
    code is what decides success."""
    cmd = [cli_path] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
    except OSError as e:
        raise SpineCliError(f"Could not run SpineViewerCLI: {e}") from e

    lines: List[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        if on_line is not None:
            on_line(line.rstrip("\n"))
    proc.wait(timeout=timeout)
    output = "".join(lines)
    if proc.returncode != 0:
        raise SpineCliError(
            f"SpineViewerCLI exited with code {proc.returncode}.\n{output.strip()[-2000:]}")
    return output


def query_model(skeleton_path, cli_path: Optional[str] = None,
                atlas_path=None, timeout: int = 120) -> ModelInfo:
    """Ask the CLI for a model's skins, animations (with durations) and slots."""
    cli_path = cli_path or find_cli()
    if not cli_path:
        raise SpineCliError("SpineViewerCLI was not found")

    args = ["query", str(skeleton_path), "--all", "-q"]
    if atlas_path:
        args += ["--atlas", str(atlas_path)]
    return parse_query_output(_run(args, cli_path, timeout=timeout))


def parse_query_output(output: str) -> ModelInfo:
    """Parse the section-delimited tables `query --all` prints."""
    section = None
    skins: List[str] = []
    animations: Dict[str, float] = {}
    slots: List[str] = []

    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = re.match(r"^>+\s*(\w+)\s*>+$", line)
        if header:
            section = header.group(1).lower()
            continue
        if re.match(r"^<+$", line):
            section = None
            continue
        if section is None:
            continue
        # Skip the column headers of each table.
        if line in ("Name", "Name\tDuration", "Name\tAttachments"):
            continue

        if section == "skins":
            skins.append(line)
        elif section == "animations":
            parts = line.split("\t")
            name = parts[0].strip()
            try:
                duration = float(parts[1]) if len(parts) > 1 else 0.0
            except ValueError:
                duration = 0.0
            if name:
                animations[name] = duration
        elif section == "slots":
            slots.append(line.split("\t")[0].strip())

    return ModelInfo(skins, animations, slots)


class ExportOptions:
    """Options for one `SpineViewerCLI export` run."""

    def __init__(self, fmt: str = "Gif", fps: int = 30, scale: float = 1.0,
                 loop: bool = True, skins: Optional[List[str]] = None,
                 background: Optional[str] = None, margin: int = 0,
                 max_resolution: int = 2048, start_time: float = 0.0,
                 duration: float = -1.0, speed: float = 1.0,
                 warm_up: float = 0.0, pma: bool = False, quality: int = 80,
                 drop_last_frame: bool = False):
        self.fmt = fmt
        self.fps = fps
        self.scale = scale
        self.loop = loop
        self.skins = skins or []
        self.background = background  # None = transparent
        self.margin = margin
        self.max_resolution = max_resolution
        self.start_time = start_time
        self.duration = duration
        self.speed = speed
        self.warm_up = warm_up
        self.pma = pma
        self.quality = quality
        self.drop_last_frame = drop_last_frame

    def to_args(self) -> List[str]:
        args: List[str] = [
            "-f", self.fmt,
            "--fps", str(self.fps),
            "--scale", str(self.scale),
            "--margin", str(self.margin),
            "--max-resolution", str(self.max_resolution),
            "--time", str(self.start_time),
            "--duration", str(self.duration),
            "--speed", str(self.speed),
            "--warm-up", str(self.warm_up),
            "--quality", str(self.quality),
        ]
        if self.loop:
            args.append("--loop")
        if self.pma:
            args.append("--pma")
        if self.drop_last_frame:
            args.append("--drop-last-frame")
        for skin in self.skins:
            args += ["--skins", skin]
        if self.background:
            args += ["--color", self.background]
        return args


def export_animation(skeleton_path, output_path, animations: List[str],
                     options: Optional[ExportOptions] = None,
                     cli_path: Optional[str] = None, atlas_path=None,
                     on_line: Optional[Callable[[str], None]] = None,
                     timeout: Optional[int] = None) -> str:
    """Export one or more animations to `output_path`. Returns that path."""
    cli_path = cli_path or find_cli()
    if not cli_path:
        raise SpineCliError("SpineViewerCLI was not found")
    if not animations:
        raise SpineCliError("No animation selected for export")

    options = options or ExportOptions()
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    args = ["export", str(skeleton_path), "-o", output_path]
    for anim in animations:
        args += ["-a", anim]
    if atlas_path:
        args += ["--atlas", str(atlas_path)]
    args += options.to_args()
    args.append("--no-progress")

    _run(args, cli_path, timeout=timeout, on_line=on_line)
    if not Path(output_path).exists():
        raise SpineCliError(f"Export reported success but no file was written: {output_path}")
    return output_path


def get_version(cli_path: Optional[str] = None) -> Optional[str]:
    cli_path = cli_path or find_cli()
    if not cli_path:
        return None
    try:
        out = _run(["--version"], cli_path, timeout=30)
        return out.strip().splitlines()[-1].strip() if out.strip() else None
    except SpineCliError:
        return None


def get_install_hint() -> str:
    return (
        "SpineViewerCLI was not found.\n\n"
        "It renders with the official Spine runtimes (2.1–4.2) and exports GIF "
        "directly, so it is more accurate and supports more Spine versions than "
        "the built-in renderer.\n\n"
        "Download it from:\n"
        "  https://github.com/ww-rm/SpineViewer/releases\n\n"
        "Then either add its folder to PATH, or point this app at "
        "SpineViewerCLI.exe with the Browse button."
    )
