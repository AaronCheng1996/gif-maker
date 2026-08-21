"""Convert finished animations (GIF, APNG, animated WebP) into video.

A GIF carries at most 256 colours and compresses each frame on its own, so a
long or large one gets very big: a 45-frame 800x570 export runs to 3.3 MB where
the same frames as H.264 are 0.58 MB at a quality indistinguishable from the
GIF. Shrinking such a file is what this module is for.

Two properties of the target format are awkward enough to be part of the API:

* **H.264 has no alpha channel.** Animations exported from Spine are routinely a
  third transparent, and there is no way to defer that decision to the player —
  a background colour has to be chosen and composited in. `VP9_ALPHA` exists for
  when the transparency genuinely has to survive, at roughly twice the size.
* **A transcode is capped by its source.** The GIF has already been quantised to
  256 colours and dithered, and no amount of bitrate brings that back. Measured
  against the frames a Spine model actually rendered, a GIF scores 17.2 dB PSNR
  and so does every video made from it, however large; encoding those frames
  straight to H.264 reaches 35.4 dB at the same size. This module is the right
  tool for a GIF you already have, not a step to put after rendering.

Nothing here imports PyQt6.
"""
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .video_to_gif import VideoConversionError, find_ffmpeg

# Constant-rate-factor values, chosen by measuring how faithfully the result
# reproduces the GIF it came from (crf 22 lands around 36 dB, crf 30 around 31).
QUALITY_PRESETS: List[Tuple[str, int]] = [
    ("Near-identical (largest)", 18),
    ("High", 22),
    ("Balanced", 26),
    ("Small", 30),
    ("Smallest (visible loss)", 34),
]
DEFAULT_CRF = 26

H264 = "H.264 / MP4"
VP9_ALPHA = "VP9 / WebM (keeps transparency)"
CODECS = [H264, VP9_ALPHA]

# Animated formats ffmpeg reads happily.
INPUT_SUFFIXES = (".gif", ".apng", ".png", ".webp")

# Only used to flatten transparency; ignored by the VP9 path.
BACKGROUND_PRESETS: List[Tuple[str, str]] = [
    ("White", "white"),
    ("Black", "black"),
    ("Magenta (easy to key out)", "magenta"),
]


def extension_for(codec: str) -> str:
    return "webm" if codec == VP9_ALPHA else "mp4"


def _ffmpeg() -> str:
    exe = find_ffmpeg()
    if exe is None:
        raise VideoConversionError(
            "ffmpeg is not installed or not found on PATH. "
            "Please install ffmpeg to convert animations to video.")
    return exe


def get_animation_info(input_path) -> dict:
    """Frame count, size and frame rate of an animated file.

    Counting frames means decoding the file, which for a GIF is cheap and is the
    only trustworthy way to get the number — the container does not store one."""
    exe = find_ffmpeg()
    if exe is None:
        return {"width": 0, "height": 0, "frames": 0, "fps": 0.0}
    probe = Path(exe).with_name("ffprobe.exe")
    if not probe.exists():
        probe = Path(exe).with_name("ffprobe")
    try:
        result = subprocess.run(
            [str(probe), "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries",
             "stream=width,height,nb_read_frames,avg_frame_rate,sample_aspect_ratio",
             "-of", "default=noprint_wrappers=1", str(input_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = result.stdout.decode(errors="ignore")
    except (OSError, subprocess.SubprocessError):
        return {"width": 0, "height": 0, "frames": 0, "fps": 0.0, "sar": "1:1"}

    def field(name: str, default: int = 0) -> int:
        m = re.search(rf"^{name}=(\d+)", text, re.MULTILINE)
        return int(m.group(1)) if m else default

    fps = 0.0
    m = re.search(r"^avg_frame_rate=(\d+)/(\d+)", text, re.MULTILINE)
    if m and int(m.group(2)):
        fps = int(m.group(1)) / int(m.group(2))
    # A sample aspect other than 1:1 means players will stretch the picture,
    # which looks like squashing plus letterbox bars even when the stored
    # dimensions are correct.
    m = re.search(r"^sample_aspect_ratio=(\S+)", text, re.MULTILINE)
    sar = m.group(1) if m and m.group(1) != "N/A" else "1:1"
    return {"width": field("width"), "height": field("height"),
            "frames": field("nb_read_frames"), "fps": fps, "sar": sar}


def _scale_chain(fps: float, width: int) -> str:
    """Frame rate and size, ending with the even dimensions both codecs demand.

    A width limit only ever shrinks. Blowing a 640px GIF up to 800 costs bitrate
    and adds blur without adding detail that was never in the source, so the
    limit is applied as a cap rather than a target."""
    steps = []
    if fps > 0:
        steps.append(f"fps={fps}")
    if width > 0:
        # The comma inside min() has to be escaped or it reads as a filter break.
        steps.append(rf"scale=w='min(iw\,{width})':h=-1:flags=lanczos")
    steps.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    return ",".join(steps)


def build_command(input_path, output_path, *, codec: str = H264, crf: int = DEFAULT_CRF,
                  background: str = "white", fps: float = 0.0, width: int = 0,
                  preset: str = "medium") -> List[str]:
    """The ffmpeg invocation for one conversion. Separated out so it can be tested."""
    chain = _scale_chain(fps, width)
    # -progress writes newline-delimited counters; the ordinary stats line is
    # carriage-return separated and would arrive as one unreadable blob.
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-nostdin",
           "-progress", "pipe:1", "-nostats", "-i", str(input_path)]

    if codec == VP9_ALPHA:
        # VP9 stores the alpha as a side stream, so the pixel format has to say
        # so both going into the encoder and coming out of it.
        cmd += ["-vf", f"{chain},setsar=1,format=yuva420p",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-crf", str(crf), "-b:v", "0", "-row-mt", "1"]
    else:
        # A colour source is scaled to the animation and laid underneath it.
        # Letting ffmpeg drop the alpha on its own fills with black instead of
        # the colour that was asked for.
        cmd += ["-f", "lavfi", "-i", f"color=c={background}",
                "-filter_complex",
                f"[0:v]{chain},format=rgba[fg];"
                f"[1:v][fg]scale2ref[bg][fg2];"
                # setsar is not optional: scale2ref matches the colour source's
                # pixel dimensions to the animation but carries its own aspect
                # over, and lavfi's colour source is 4:3. Without this the file
                # claims non-square pixels, and players squash the picture and
                # letterbox it even though the stored size is right.
                f"[bg][fg2]overlay=shortest=1,setsar=1,format=yuv420p[v]",
                "-map", "[v]",
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    cmd.append(str(output_path))
    return cmd


def convert_to_video(input_path, output_path=None, *, codec: str = H264,
                     crf: int = DEFAULT_CRF, background: str = "white",
                     fps: float = 0.0, width: int = 0, preset: str = "medium",
                     on_progress: Optional[Callable[[int], None]] = None,
                     should_stop: Optional[Callable[[], bool]] = None) -> str:
    """Convert one animated file to MP4 (H.264) or WebM (VP9 with alpha).

    `background` is anything ffmpeg accepts ("white", "#204060") and shows
    wherever the source was transparent; the VP9 path keeps the transparency and
    ignores it. `crf` is a quality target rather than a size target, so the
    resulting size follows from how much detail the source holds.

    Returns the path written."""
    source = Path(input_path)
    if not source.exists():
        raise VideoConversionError(f"Input file not found: {source}")
    if codec not in CODECS:
        raise VideoConversionError(f"Unknown codec: {codec}")

    out = Path(output_path) if output_path else \
        source.with_suffix(f".{extension_for(codec)}")
    if out.resolve() == source.resolve():
        raise VideoConversionError("Refusing to overwrite the source file")
    out.parent.mkdir(parents=True, exist_ok=True)

    total = get_animation_info(source).get("frames", 0)
    cmd = build_command(source, out, codec=codec, crf=crf, background=background,
                        fps=fps, width=width, preset=preset)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, text=True,
                                encoding="utf-8", errors="replace")
    except OSError as e:
        raise VideoConversionError(f"Could not run ffmpeg: {e}") from e

    log: List[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        log.append(line)
        if should_stop is not None and should_stop():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise VideoConversionError("Cancelled")
        if on_progress is not None and total:
            m = re.search(r"frame=\s*(\d+)", line)
            if m:
                on_progress(min(int(m.group(1)) * 100 // total, 100))
    proc.wait()
    if proc.returncode != 0 or not out.exists():
        raise VideoConversionError(
            f"ffmpeg failed (code {proc.returncode}).\n{''.join(log).strip()[-1500:]}")
    if on_progress is not None:
        on_progress(100)
    return str(out)


def size_change(source, produced) -> Tuple[int, int, float]:
    """(source bytes, produced bytes, how many times smaller the result is)."""
    a = Path(source).stat().st_size
    b = Path(produced).stat().st_size
    return a, b, (a / b if b else 0.0)
