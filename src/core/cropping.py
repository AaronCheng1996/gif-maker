"""Crop an animation file to a sub-rectangle.

Crops are expressed as normalized (x, y, w, h) in 0..1 with the origin at the
top left, so the same rectangle applies to files of any size. Frame-based
formats (gif/apng/webp) go through Pillow; video formats go through ffmpeg.
"""
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageSequence

PIL_FORMATS = {".gif", ".png", ".webp"}
VIDEO_FORMATS = {".mp4", ".mov", ".webm", ".mkv"}

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class CropError(Exception):
    pass


def pixel_box(width: int, height: int, crop: Tuple[float, float, float, float]
              ) -> Tuple[int, int, int, int]:
    """Turn a normalized (x, y, w, h) crop into an integer (left, top, right, bottom)."""
    cx, cy, cw, ch = crop
    left = max(0, min(int(round(cx * width)), width - 1))
    top = max(0, min(int(round(cy * height)), height - 1))
    right = max(left + 1, min(int(round((cx + cw) * width)), width))
    bottom = max(top + 1, min(int(round((cy + ch) * height)), height))
    return left, top, right, bottom


def is_noop(crop: Optional[Tuple[float, float, float, float]]) -> bool:
    if crop is None:
        return True
    cx, cy, cw, ch = crop
    return cx <= 0.001 and cy <= 0.001 and cw >= 0.999 and ch >= 0.999


def crop_animation_file(path, crop: Tuple[float, float, float, float],
                        ffmpeg_path: Optional[str] = None,
                        output_path=None) -> str:
    """Crop `path` to the normalized rectangle `crop`.

    Writes to `output_path` when given, otherwise replaces the file in place.
    Returns the path written."""
    path = Path(path)
    if not path.exists():
        raise CropError(f"File not found: {path}")
    destination = Path(output_path) if output_path else path
    if is_noop(crop):
        if destination != path:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        return str(destination)

    suffix = path.suffix.lower()
    if suffix in PIL_FORMATS:
        return _crop_with_pil(path, crop, destination)
    if suffix in VIDEO_FORMATS:
        return _crop_with_ffmpeg(path, crop, ffmpeg_path, destination)
    raise CropError(f"Cropping is not supported for {suffix} files")


def _crop_with_pil(path: Path, crop, destination: Path) -> str:
    with Image.open(path) as src:
        box = pixel_box(src.width, src.height, crop)
        is_animated = getattr(src, "is_animated", False)
        info = dict(src.info)
        frames: List[Image.Image] = []
        durations: List[int] = []
        for frame in ImageSequence.Iterator(src):
            durations.append(frame.info.get("duration", info.get("duration", 100)))
            # Compose to RGBA first: GIF frames can be partial updates, and
            # cropping a delta frame directly would lose the pixels underneath.
            frames.append(frame.convert("RGBA").crop(box))

    if not frames:
        raise CropError("No frames to crop")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the destination first so a failure cannot leave a half-written
    # file where the caller expects a good one.
    tmp = destination.with_name(destination.stem + "__cropped" + destination.suffix)
    fmt = path.suffix.lower().lstrip(".")
    save_kwargs = {}
    if is_animated:
        save_kwargs.update(save_all=True, append_images=frames[1:], duration=durations)
        loop = info.get("loop")
        if loop is not None:
            save_kwargs["loop"] = loop

    if fmt == "gif":
        converted = [_to_palette(f) for f in frames]
        save_kwargs["disposal"] = 2
        save_kwargs["optimize"] = False
        if is_animated:
            save_kwargs["append_images"] = converted[1:]
        converted[0].save(tmp, format="GIF", transparency=255, **save_kwargs)
    elif fmt == "webp":
        frames[0].save(tmp, format="WEBP", lossless=True, **save_kwargs)
    else:  # png / apng
        frames[0].save(tmp, format="PNG", **save_kwargs)

    tmp.replace(destination)
    return str(destination)


def _to_palette(img: Image.Image) -> Image.Image:
    """Quantize an RGBA frame for GIF, reserving index 255 for transparency."""
    alpha = img.getchannel("A")
    out = img.convert("RGB").convert(
        "P", palette=Image.Palette.ADAPTIVE, colors=255)
    mask = alpha.point(lambda a: 255 if a < 128 else 0)
    out.paste(255, mask)
    return out


def _crop_with_ffmpeg(path: Path, crop, ffmpeg_path: Optional[str],
                      destination: Path) -> str:
    exe = ffmpeg_path or shutil.which("ffmpeg")
    if not exe:
        raise CropError(
            "Cropping video output needs ffmpeg, which was not found on PATH.")
    cx, cy, cw, ch = crop
    # Expressed against ffmpeg's own iw/ih so the file needs no probing, and
    # rounded to even dimensions because most codecs require it.
    crop_expr = (f"crop=trunc(iw*{cw:.6f}/2)*2:trunc(ih*{ch:.6f}/2)*2"
                 f":trunc(iw*{cx:.6f}):trunc(ih*{cy:.6f})")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.stem + "__cropped" + destination.suffix)
    cmd = [exe, "-y", "-i", str(path), "-vf", crop_expr, "-c:a", "copy", str(tmp)]
    try:
        # ffmpeg writes UTF-8; without saying so Python decodes with the console
        # codepage and dies in its reader thread, turning a real ffmpeg error
        # message into an unrelated UnicodeDecodeError.
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              creationflags=_CREATE_NO_WINDOW)
    except OSError as e:
        raise CropError(f"Could not run ffmpeg: {e}") from e
    if proc.returncode != 0 or not tmp.exists():
        raise CropError(f"ffmpeg failed to crop:\n{proc.stderr[-1500:]}")
    tmp.replace(destination)
    return str(destination)
