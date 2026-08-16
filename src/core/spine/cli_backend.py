"""Drive SpineViewerCLI.exe as an export backend.

SpineViewerCLI (https://github.com/ww-rm/SpineViewer) bundles the official Spine
runtimes (2.1 through 4.2) plus its own ffmpeg, and can export straight to GIF —
so when it is available it renders more accurately and covers far more Spine
versions than the built-in Python runtime, and needs no intermediate MP4.

This module only shells out to it; nothing here imports PyQt6.
"""
import copy
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

EXE_NAME = "SpineViewerCLI.exe" if sys.platform == "win32" else "SpineViewerCLI"

# Formats the CLI accepts for -f. GIF is what this app cares about, but the
# others are handy for users who want a lossless master alongside the GIF.
# Png and Jpg write a single still rather than an animation.
EXPORT_FORMATS = ["Gif", "Apng", "Webp", "Webpa", "Png", "Jpg", "Frames",
                  "Mp4", "Mov", "Webm", "Mkv"]

# The two formats above that produce one frame instead of a sequence.
STILL_FORMATS = frozenset({"Png", "Jpg"})

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
                 drop_last_frame: bool = False,
                 disabled_slots: Optional[List[str]] = None):
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
        # Slots to leave unrendered — how stray shadows, masks and signature
        # layers get taken out of an export.
        self.disabled_slots = disabled_slots or []

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
        for slot in self.disabled_slots:
            args += ["--disable-slots", slot]
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


def render_frame_sequence(skeleton_path, output_dir, animation: str,
                          options: Optional[ExportOptions] = None,
                          cli_path: Optional[str] = None, atlas_path=None,
                          on_frame: Optional[Callable[[int, Path], None]] = None,
                          should_stop: Optional[Callable[[], bool]] = None,
                          poll_interval: float = 0.05,
                          timeout: Optional[int] = None) -> List[Path]:
    """Render one animation to a folder of PNGs, reporting frames as they land.

    `-f Frames` writes its folder one file at a time instead of all at the end,
    and does so faster than the animation plays, so a caller can put the first
    frame on screen about a second in and let the rest fill in behind it.
    `on_frame(index, path)` is called once per file, in frame order.

    Returns the frame paths. When `should_stop` starts returning True the CLI is
    terminated and whatever had been rendered so far is returned."""
    cli_path = cli_path or find_cli()
    if not cli_path:
        raise SpineCliError("SpineViewerCLI was not found")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    options = copy.copy(options) if options is not None else ExportOptions()
    options.fmt = "Frames"

    args = ["export", str(skeleton_path), "-o", str(output_dir), "-a", animation]
    if atlas_path:
        args += ["--atlas", str(atlas_path)]
    args += options.to_args()
    args.append("--no-progress")

    try:
        proc = subprocess.Popen(
            [cli_path] + args,
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

    log: List[str] = []
    reader = threading.Thread(target=log.extend, args=(proc.stdout,), daemon=True)
    reader.start()

    frames: List[Path] = []

    def collect(finished: bool):
        try:
            current = sorted(output_dir.glob("*.png"))
        except OSError:
            return
        # The newest file may still be half-written, so it is held back until
        # another one appears after it (or the CLI exits).
        ready = current if finished else current[:-1]
        for path in ready[len(frames):]:
            frames.append(path)
            if on_frame is not None:
                on_frame(len(frames) - 1, path)

    deadline = time.monotonic() + timeout if timeout else None
    while proc.poll() is None:
        if should_stop is not None and should_stop():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return frames
        if deadline is not None and time.monotonic() > deadline:
            proc.kill()
            proc.wait()
            raise SpineCliError(f"SpineViewerCLI timed out after {timeout}s")
        collect(False)
        time.sleep(poll_interval)

    reader.join(timeout=5)
    collect(True)
    if proc.returncode != 0:
        raise SpineCliError(
            f"SpineViewerCLI exited with code {proc.returncode}.\n"
            f"{''.join(log).strip()[-2000:]}")
    return frames


class Framing:
    """Where SpineViewerCLI puts the canvas, measured rather than predicted.

    SpineViewer picks its own canvas, and the rule is not something we can infer
    reliably (it is neither the skeleton's declared bounds nor a tight fit around
    the animation). Since the crop rectangle has to line up with its output, the
    canvas is measured by exporting one small frame and looking at it."""

    __slots__ = ("canvas_w_px", "canvas_h_px", "content_box_px", "scale")

    def __init__(self, canvas_w_px: int, canvas_h_px: int,
                 content_box_px: Optional[Tuple[int, int, int, int]], scale: float):
        self.canvas_w_px = canvas_w_px
        self.canvas_h_px = canvas_h_px
        self.content_box_px = content_box_px   # (left, top, right, bottom) or None
        self.scale = scale

    def canvas_size_units(self) -> Tuple[float, float]:
        return self.canvas_w_px / self.scale, self.canvas_h_px / self.scale


PROBE_EXTENSIONS = {
    "Gif": "gif", "Apng": "png", "Webp": "webp", "Webpa": "webp", "Png": "png",
    "Jpg": "jpg", "Mp4": "mp4", "Mov": "mov", "Webm": "webm", "Mkv": "mkv",
}


def probe_framing(skeleton_path, animation: str, skin: Optional[str] = None,
                  cli_path: Optional[str] = None, atlas_path=None,
                  scale: float = 0.12, fmt: str = "Gif", timeout: int = 300) -> Framing:
    """Export one small file and measure the canvas the CLI chose.

    The format matters: SpineViewer sizes its canvas slightly differently for a
    single still than for an animation, so probing must use the same format the
    real export will, or the crop rectangle drifts."""
    import tempfile

    from PIL import Image

    cli_path = cli_path or find_cli()
    if not cli_path:
        raise SpineCliError("SpineViewerCLI was not found")

    if fmt not in PROBE_EXTENSIONS or fmt in ("Mp4", "Mov", "Webm", "Mkv"):
        fmt = "Gif"   # video probes cannot be measured with Pillow
    tmpdir = tempfile.mkdtemp(prefix="spine_probe_")
    out = Path(tmpdir) / f"probe.{PROBE_EXTENSIONS[fmt]}"
    try:
        # A couple of frames per second is enough to establish the canvas.
        options = ExportOptions(fmt=fmt, scale=scale, loop=False, fps=2,
                                skins=[skin] if skin else [],
                                start_time=0.0, max_resolution=20000)
        export_animation(skeleton_path, out, [animation], options=options,
                         cli_path=cli_path, atlas_path=atlas_path, timeout=timeout)
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            with Image.open(out) as img:
                rgba = img.convert("RGBA")
                width, height = rgba.size
                box = rgba.getbbox()   # None when fully transparent
        finally:
            Image.MAX_IMAGE_PIXELS = previous_limit
        return Framing(width, height, box, scale)
    finally:
        try:
            if out.exists():
                out.unlink()
            Path(tmpdir).rmdir()
        except OSError:
            pass


def framing_to_bounds(framing: Framing, content_bounds) -> Tuple[float, float, float, float]:
    """Turn a measured canvas into skeleton-space bounds the renderer can use.

    `content_bounds` is (x, y, w, h) of the same pose as rendered by the built-in
    engine. Lining up where the content sits in both images pins down where the
    CLI's canvas is; its size comes straight from the probe."""
    canvas_w, canvas_h = framing.canvas_size_units()
    cx, cy, cw, ch = content_bounds
    if not framing.content_box_px or cw <= 0 or ch <= 0:
        # Nothing visible to align against; centre the canvas on the content.
        return (cx + cw / 2 - canvas_w / 2, cy + ch / 2 - canvas_h / 2, canvas_w, canvas_h)

    left, top, _right, _bottom = framing.content_box_px
    origin_x = cx - left / framing.scale
    # Image rows run downwards, so the canvas top edge is the highest skeleton Y.
    origin_y = (cy + ch) + top / framing.scale - canvas_h
    return origin_x, origin_y, canvas_w, canvas_h


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
