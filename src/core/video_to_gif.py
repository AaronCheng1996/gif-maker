from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image


class VideoConversionError(Exception):
    """Raised when video-to-GIF conversion fails."""


def get_ffmpeg_install_info() -> dict:
    """Return platform-specific instructions for installing ffmpeg.

    Returns a dict with keys:
        platform  – human-readable OS name
        method    – short description of the recommended method
        command   – shell command the user can run (empty if not applicable)
        url       – download/doc URL for manual installation
        note      – extra context (e.g. winget vs. manual)
    """
    platform = sys.platform
    if platform == "win32":
        return {
            "platform": "Windows",
            "method": "winget (recommended) or manual download",
            "command": "winget install --id Gyan.FFmpeg -e",
            "url": "https://www.gyan.dev/ffmpeg/builds/",
            "note": (
                "After installation you may need to restart the application "
                "for PATH changes to take effect."
            ),
        }
    elif platform == "darwin":
        return {
            "platform": "macOS",
            "method": "Homebrew",
            "command": "brew install ffmpeg",
            "url": "https://ffmpeg.org/download.html#build-mac",
            "note": (
                "Install Homebrew first from https://brew.sh if you don't have it."
            ),
        }
    else:
        # Linux / other Unix
        import distro as _distro  # optional dep; fall back to lsb_release
        try:
            distro_id = _distro.id().lower()
        except Exception:
            distro_id = ""

        if distro_id in ("ubuntu", "debian", "linuxmint", "pop"):
            cmd = "sudo apt update && sudo apt install -y ffmpeg"
        elif distro_id in ("fedora", "rhel", "centos", "rocky", "alma"):
            cmd = "sudo dnf install -y ffmpeg"
        elif distro_id in ("arch", "manjaro", "endeavouros"):
            cmd = "sudo pacman -S ffmpeg"
        else:
            cmd = "sudo apt install ffmpeg  # or use your distro's package manager"

        return {
            "platform": "Linux",
            "method": "system package manager",
            "command": cmd,
            "url": "https://ffmpeg.org/download.html#build-linux",
            "note": "Command may vary depending on your Linux distribution.",
        }


def _windows_registry_path() -> str:
    """Read the current User + System PATH from the Windows registry.

    winget (and other installers) write to the registry; the running process
    only sees the PATH that was active at launch.  Reading the registry gives
    us the up-to-date value without requiring an app restart.
    """
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        parts: list[str] = []
        # User PATH
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                val, _ = winreg.QueryValueEx(k, "PATH")
                parts.append(os.path.expandvars(val))
        except OSError:
            pass
        # System PATH
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            ) as k:
                val, _ = winreg.QueryValueEx(k, "Path")
                parts.append(os.path.expandvars(val))
        except OSError:
            pass
        return os.pathsep.join(parts)
    except Exception:
        return ""


def find_ffmpeg() -> Optional[str]:
    """Return the full path to the ffmpeg executable, or None if not found.

    Checks (in order):
    1. The process's current PATH (fast, works when PATH is already correct).
    2. The Windows registry PATH (catches installs done after app launch, e.g. winget).
    """
    # 1. Current process PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 2. Windows registry PATH (post-launch installs)
    reg_path = _windows_registry_path()
    if reg_path:
        found = shutil.which("ffmpeg", path=reg_path)
        if found:
            # Propagate into the process environment so subsequent calls work
            os.environ["PATH"] = reg_path + os.pathsep + os.environ.get("PATH", "")
            return found
    return None


def is_ffmpeg_available() -> bool:
    """Return True if ffmpeg can be located (checks registry PATH on Windows)."""
    return find_ffmpeg() is not None


def _ffmpeg() -> str:
    """Return the resolved ffmpeg path, raising VideoConversionError if absent."""
    exe = find_ffmpeg()
    if exe is None:
        raise VideoConversionError(
            "ffmpeg is not installed or not found on PATH. "
            "Please install ffmpeg to use video conversion features."
        )
    return exe


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, raising VideoConversionError on failure."""
    try:
        return subprocess.run(
            cmd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        raise VideoConversionError(
            f"{cmd[0]} failed (code {e.returncode}): "
            f"{e.stderr.decode(errors='ignore').strip()}"
        )
    except FileNotFoundError:
        raise VideoConversionError(f"{cmd[0]} not found on PATH")


def get_video_info(input_path: str) -> dict:
    """Return basic metadata for the given video/animated-image file.

    Returns a dict with keys: width, height, fps (float), duration (float, seconds).
    Falls back to 0/0.0 for fields that cannot be parsed.
    """
    exe = find_ffmpeg()
    if exe is None:
        return {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0,
                "error": "ffmpeg not found"}
    try:
        result = subprocess.run(
            [exe, "-i", input_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stderr = result.stderr.decode(errors="ignore")
    except FileNotFoundError:
        return {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0}

    width = height = 0
    fps = duration = 0.0

    # Duration: "Duration: HH:MM:SS.ss"
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        duration = h * 3600 + mn * 60 + s

    # Video stream resolution and fps
    # e.g. "Stream #0:0: Video: h264, yuv420p, 1920x1080, 30 fps"
    m = re.search(r"(\d{2,5})x(\d{2,5})", stderr)
    if m:
        width, height = int(m.group(1)), int(m.group(2))

    m = re.search(r"([\d.]+)\s*(?:fps|tb\(r\))", stderr)
    if m:
        fps = float(m.group(1))

    return {"width": width, "height": height, "fps": fps, "duration": duration}


def extract_first_frame(input_path: str) -> Image.Image:
    """Extract the first frame of a video/animated file as a PIL Image."""
    result = _run([
        _ffmpeg(), "-i", input_path,
        "-frames:v", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "pipe:1",
    ])
    return Image.open(io.BytesIO(result.stdout)).convert("RGBA")


def extract_preview_frames(
    input_path: str,
    fps: float = 10.0,
    max_width: int = 480,
    max_duration: float = 10.0,
    start_time: float = 0.0,
    end_time: float = 0.0,
) -> list[tuple[Image.Image, int]]:
    """Extract animated preview frames from a video/animated-image file.

    Extracts up to `max_duration` seconds at `fps` frames per second,
    scaling to at most `max_width` pixels wide (aspect-ratio preserved).
    Returns a list of (PIL.Image RGBA, duration_ms) tuples suitable for
    PreviewWidget.set_frames().
    """
    input_args: list[str] = []
    if start_time > 0:
        input_args += ["-ss", str(start_time)]

    # How long to extract: cap at max_duration
    clip_len = (end_time - start_time) if (end_time > start_time) else max_duration
    clip_len = min(clip_len, max_duration)
    input_args += ["-t", str(clip_len)]

    scale_filter = f"scale='min({max_width},iw)':-2:flags=lanczos" if max_width > 0 else ""
    vf = f"fps={fps}"
    if scale_filter:
        vf += f",{scale_filter}"

    with tempfile.TemporaryDirectory() as tmpdir:
        pattern = str(Path(tmpdir) / "frame_%05d.png")
        _run([
            _ffmpeg(),
            *input_args, "-i", input_path,
            "-vf", vf,
            "-f", "image2",
            "-y", pattern,
        ])
        frame_files = sorted(Path(tmpdir).glob("frame_*.png"))
        duration_ms = max(10, int(1000 / fps))
        frames: list[tuple[Image.Image, int]] = []
        for f in frame_files:
            try:
                img = Image.open(f).convert("RGBA")
                frames.append((img.copy(), duration_ms))
            except Exception:
                pass
    return frames


def convert_to_gif(
    input_path: str,
    output_path: Optional[str] = None,
    fps: float = 10.0,
    width: int = 0,
    start_time: float = 0.0,
    end_time: float = 0.0,
    colors: int = 256,
    dither: str = "bayer",
    lossy: int = 0,
    overwrite: bool = False,
) -> str:
    """Convert a video or animated-image file to a GIF.

    Uses a two-pass ffmpeg palettegen approach for maximum quality, matching
    ezgif's conversion strategy. Optionally runs a gifsicle lossy post-pass.

    Args:
        input_path: Source file (mp4, mov, webm, webp, gif, apng, etc.)
        output_path: Destination .gif path. If None, derives from input.
        fps: Output frame rate (1–60).
        width: Output width in pixels. 0 = keep source dimensions.
        start_time: Trim start in seconds. 0 = from beginning.
        end_time: Trim end in seconds. 0 = until end of file.
        colors: Palette size (32–256).
        dither: Dithering algorithm: bayer, floyd_steinberg, sierra2, none.
        lossy: gifsicle lossy value (0 = skip). Requires gifsicle on PATH.
        overwrite: When True and output_path is None, replace the input file.

    Returns:
        Path to the produced GIF file.
    """
    ffmpeg_exe = _ffmpeg()  # raises VideoConversionError if not found

    src = Path(input_path)
    if not src.exists():
        raise VideoConversionError(f"Input file does not exist: {input_path}")

    if output_path:
        dst = Path(output_path)
    elif overwrite:
        dst = src.with_suffix(".gif")
    else:
        dst = src.with_name(src.stem + ".gif")
        if dst == src:
            dst = src.with_name(src.stem + "-converted.gif")

    dst.parent.mkdir(parents=True, exist_ok=True)

    colors = max(2, min(256, colors))
    fps = max(1.0, min(60.0, fps))

    # Build shared seek/duration args
    input_args: list[str] = []
    if start_time > 0:
        input_args += ["-ss", str(start_time)]
    if end_time > 0 and end_time > start_time:
        input_args += ["-t", str(end_time - start_time)]

    # Build scale filter component (omit entirely when width=0)
    if width > 0:
        # -2 ensures the scaled dimension is even (required by some codecs)
        scale_filter = f",scale={width}:-2:flags=lanczos"
    else:
        scale_filter = ""

    # Build paletteuse dither options
    if dither == "bayer":
        dither_opts = "dither=bayer:bayer_scale=5:diff_mode=rectangle"
    elif dither == "none":
        dither_opts = "dither=none:diff_mode=rectangle"
    else:
        dither_opts = f"dither={dither}:diff_mode=rectangle"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        palette_png = str(tmp_dir / "palette.png")
        tmp_gif = str(tmp_dir / "output.gif")

        # Pass 1: generate per-video palette
        _run([
            ffmpeg_exe,
            *input_args, "-i", str(src),
            "-vf", f"fps={fps}{scale_filter},palettegen=max_colors={colors}:stats_mode=diff",
            "-y", palette_png,
        ])

        # Pass 2: encode GIF with the generated palette
        # [0:v] prefix is required when there are two inputs to avoid ambiguity
        _run([
            ffmpeg_exe,
            *input_args, "-i", str(src), "-i", palette_png,
            "-filter_complex",
            f"[0:v]fps={fps}{scale_filter}[x];[x][1:v]paletteuse={dither_opts}",
            "-y", tmp_gif,
        ])

        # Optional gifsicle lossy post-pass
        if lossy > 0 and shutil.which("gifsicle"):
            lossy = max(0, min(200, lossy))
            try:
                subprocess.run(
                    ["gifsicle", f"--lossy={lossy}", "-O3", tmp_gif, "-o", tmp_gif],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError:
                pass  # lossy pass is best-effort; keep uncompressed result

        # shutil.move handles cross-drive moves (os.rename/replace cannot)
        shutil.move(tmp_gif, str(dst))

    return str(dst)
