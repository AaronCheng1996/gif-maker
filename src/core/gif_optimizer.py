from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image


class GifOptimizationError(Exception):
    """Raised when GIF optimization fails."""


def is_gifsicle_available() -> bool:
    """Return True if gifsicle is available on PATH."""
    return shutil.which("gifsicle") is not None


def _optimize_with_gifsicle(input_path: str, output_path: str, lossy: int, colors: Optional[int]) -> None:
    if lossy < 0:
        lossy = 0
    if lossy > 200:
        lossy = 200

    cmd = [
        "gifsicle",
        f"--lossy={lossy}",
        "-O3",
    ]

    if colors is not None:
        # Limit palette if requested
        cmd += ["--colors", str(colors)]

    cmd += [input_path, "-o", output_path]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise GifOptimizationError(
            f"gifsicle failed (code {e.returncode}): {e.stderr.decode(errors='ignore').strip()}"
        )
    except Exception as e:
        # Wrap any unexpected invocation errors
        raise GifOptimizationError(f"gifsicle invocation failed: {e}")

    # Ensure output file was actually produced
    if not Path(output_path).exists():
        raise GifOptimizationError("gifsicle did not produce the expected output file")


def _optimize_with_pillow(input_path: str, output_path: str, colors: Optional[int]) -> None:
    # Fallback: re-save with optimized palette via Pillow. This is not true lossy giflossy,
    # but provides some size reduction when gifsicle is unavailable.
    with Image.open(input_path) as im:
        frames = []
        durations = []
        try:
            while True:
                frame = im.convert("RGBA")
                if colors:
                    # Quantize reduces palette size
                    frame = frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=colors)
                frames.append(frame)
                durations.append(im.info.get("duration", 100))
                im.seek(im.tell() + 1)
        except EOFError:
            pass

        if not frames:
            raise GifOptimizationError("Input GIF has no frames")

        first = frames[0]
        append = frames[1:] if len(frames) > 1 else []
        first.save(
            output_path,
            format="GIF",
            save_all=True,
            append_images=append,
            duration=durations,
            loop=0,
            optimize=True,
            disposal=2,
        )


def optimize_gif_lossy(
    input_path: str,
    output_path: Optional[str] = None,
    lossy: int = 80,
    colors: Optional[int] = None,
    overwrite: bool = False,
) -> str:
    """
    Optimize a GIF using gifsicle's lossy compression if available.

    Args:
        input_path: Source GIF file.
        output_path: Destination GIF file. If None, will overwrite input when overwrite=True
                     or create alongside input with suffix "-optimized.gif".
        lossy: gifsicle lossy value (0-200). Higher is more compression.
        colors: Optional palette size to limit (e.g. 256, 128, 64...).
        overwrite: When True and output_path is None, replace the input atomically.

    Returns:
        The path to the optimized GIF.
    """
    src = Path(input_path)
    if not src.exists():
        raise GifOptimizationError(f"Input file does not exist: {input_path}")

    if output_path:
        dst = Path(output_path)
    else:
        if overwrite:
            dst = src
        else:
            dst = src.with_name(src.stem + "-optimized.gif")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first for safety, then move/replace
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_out = Path(tmpdir) / (dst.name + ".tmp")

        if is_gifsicle_available():
            _optimize_with_gifsicle(str(src), str(tmp_out), lossy=lossy, colors=colors)
        else:
            _optimize_with_pillow(str(src), str(tmp_out), colors=colors)

        # Atomic replace if overwriting; else move
        if dst.exists():
            tmp_out.replace(dst)
        else:
            tmp_out.rename(dst)

    return str(dst)


