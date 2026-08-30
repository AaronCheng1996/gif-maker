"""Join several animations or videos end to end into one file.

Joining is only trivial when the parts already match. ffmpeg's concat filter
refuses inputs that disagree on size, pixel format or sample aspect, and a
sequence assembled from a GIF, a phone clip and a screen capture never agrees on
any of them. So every part is normalised to one geometry and frame rate first,
and the interesting question is what "normalised" should mean:

* **Size** is padded, never stretched. Scaling a 4:3 clip into a 16:9 slot to
  make the numbers line up distorts everyone in it; fitting it and filling the
  rest is the only version that stays honest about the source.
* **Sample aspect** is forced to 1:1 on every part. A file that claims non-square
  pixels plays back squashed even when its stored dimensions are right, and one
  such part poisons the whole join.
* **Frame rate** is levelled up rather than down by default, so the smoothest
  part keeps its motion instead of being decimated to match the worst one.

Nothing here imports PyQt6.
"""
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .proc import popen_hidden, run_hidden
from .video_to_gif import VideoConversionError, find_ffmpeg

# Anything ffmpeg reads and the rest of the app already deals in.
INPUT_SUFFIXES = (".gif", ".apng", ".png", ".webp",
                  ".mp4", ".mov", ".webm", ".mkv", ".avi")

MP4 = "MP4 (H.264)"
GIF = "GIF"
OUTPUTS = [MP4, GIF]

# Padding colour, and what transparency is flattened onto for MP4.
BACKGROUND_PRESETS: List[Tuple[str, str]] = [
    ("Black", "black"),
    ("White", "white"),
    ("Magenta (easy to key out)", "magenta"),
]

MATCH_FIRST = "Match the first file"
MATCH_LARGEST = "Fit the largest file"
SIZE_MODES = [MATCH_FIRST, MATCH_LARGEST]

DEFAULT_CRF = 23


class ConcatError(VideoConversionError):
    """Raised when a join cannot be planned or ffmpeg refuses it."""


def extension_for(output: str) -> str:
    return "gif" if output == GIF else "mp4"


def _ffmpeg() -> str:
    exe = find_ffmpeg()
    if exe is None:
        raise ConcatError(
            "ffmpeg is not installed or not found on PATH. "
            "Please install ffmpeg to join videos.")
    return exe


def _ffprobe() -> Optional[str]:
    exe = find_ffmpeg()
    if exe is None:
        return None
    probe = Path(exe).with_name("ffprobe.exe")
    if not probe.exists():
        probe = Path(exe).with_name("ffprobe")
    return str(probe) if probe.exists() else None


def probe(path) -> dict:
    """Size, frame rate, duration and whether the file carries sound.

    Deliberately does not count frames. `get_animation_info` in gif_to_mp4 does,
    because a GIF stores no frame count and its caller needs one — but that
    means decoding the whole file, and a join is normally several long clips
    where the wait would be obvious and the number is not needed anyway.
    """
    blank = {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0,
             "has_audio": False, "sar": "1:1"}
    exe = _ffprobe()
    if exe is None:
        return blank
    try:
        result = run_hidden(
            [exe, "-v", "error",
             "-show_entries", "stream=codec_type,width,height,avg_frame_rate,"
                              "sample_aspect_ratio",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = result.stdout.decode(errors="replace")
    except (OSError, subprocess.SubprocessError):
        return blank

    info = dict(blank)
    info["has_audio"] = "codec_type=audio" in text
    m = re.search(r"^width=(\d+)", text, re.MULTILINE)
    if m:
        info["width"] = int(m.group(1))
    m = re.search(r"^height=(\d+)", text, re.MULTILINE)
    if m:
        info["height"] = int(m.group(1))
    m = re.search(r"^duration=([\d.]+)", text, re.MULTILINE)
    if m:
        info["duration"] = float(m.group(1))
    m = re.search(r"^avg_frame_rate=(\d+)/(\d+)", text, re.MULTILINE)
    if m and int(m.group(2)):
        info["fps"] = int(m.group(1)) / int(m.group(2))
    m = re.search(r"^sample_aspect_ratio=(\S+)", text, re.MULTILINE)
    if m and m.group(1) != "N/A":
        info["sar"] = m.group(1)
    return info


class Segment:
    """One entry on the timeline: a file, and optionally a slice of it.

    The same file can appear more than once with different in and out points,
    which is why the timeline is a list of these rather than a list of paths —
    a library entry is the material, a segment is a use of it.

    `end` of 0 means "run to the end of the source", so a freshly added segment
    needs no probing to be valid and stays correct if the file is replaced.
    """

    def __init__(self, path, start: float = 0.0, end: float = 0.0,
                 info: Optional[dict] = None):
        self.path = Path(path)
        self.start = max(0.0, float(start))
        self.end = max(0.0, float(end))
        self.info = probe(self.path) if info is None else info

    @property
    def source_duration(self) -> float:
        return float(self.info.get("duration") or 0.0)

    @property
    def out_point(self) -> float:
        end = self.end if self.end > 0 else self.source_duration
        return min(end, self.source_duration) if self.source_duration else end

    @property
    def duration(self) -> float:
        return max(0.0, self.out_point - self.start)

    @property
    def trimmed(self) -> bool:
        return self.start > 0.0 or 0.0 < self.end < self.source_duration - 1e-6

    def label(self) -> str:
        if not self.trimmed:
            return self.path.name
        return f"{self.path.name}  [{self.start:.2f}s – {self.out_point:.2f}s]"


def as_segments(items: Sequence) -> List[Segment]:
    """Accept a timeline of Segments, or bare paths for the untrimmed case."""
    return [i if isinstance(i, Segment) else Segment(i) for i in items]


def _even(n: int) -> int:
    """H.264's 4:2:0 chroma cannot describe odd dimensions."""
    return max(2, n - (n % 2))


def plan(segments: Sequence[Segment], *, size_mode: str = MATCH_FIRST,
         fps: float = 0.0, max_width: int = 0) -> dict:
    """Work out the one geometry and frame rate every part will be brought to.

    Returned separately from the command so the UI can say what will happen
    before anything runs — which parts get padded, and whether sound survives.
    """
    segments = as_segments(segments)
    infos = [s.info for s in segments]
    usable = [i for i in infos if i.get("width") and i.get("height")]
    if not usable:
        raise ConcatError("None of these files could be read by ffmpeg")

    if size_mode == MATCH_LARGEST:
        width = max(i["width"] for i in usable)
        height = max(i["height"] for i in usable)
    else:
        width, height = usable[0]["width"], usable[0]["height"]

    if max_width and width > max_width:
        # Only ever downwards, and the height follows so nothing is distorted.
        # Used for the preview render, which wants the real timing and framing
        # at a size that encodes in a moment.
        height = max(1, round(height * max_width / width))
        width = max_width
    width, height = _even(width), _even(height)

    rate = fps if fps > 0 else max((i.get("fps") or 0.0) for i in usable)
    if rate <= 0:
        rate = 15.0

    # Sound only survives if every part has some. Concatenating a clip that has
    # audio with one that does not leaves the join out of sync from that point
    # on, so the honest options are all-or-nothing.
    keep_audio = bool(usable) and all(i.get("has_audio") for i in infos)

    return {
        "width": width,
        "height": height,
        "fps": round(rate, 3),
        "keep_audio": keep_audio,
        # Trimmed lengths, not source lengths: this is what the progress bar
        # measures against, and it is what the join will actually last.
        "duration": sum(s.duration for s in segments),
        "padded": [bool(i.get("width")) and
                   (i["width"], i["height"]) != (width, height) for i in infos],
    }


def build_command(segments: Sequence, output_path, *, layout: dict,
                  output: str = MP4, background: str = "black",
                  crf: int = DEFAULT_CRF, preset: str = "medium") -> List[str]:
    """The ffmpeg invocation for one join. Separated out so it can be tested."""
    segments = as_segments(segments)
    if not segments:
        raise ConcatError("Nothing to join")

    w, h, fps = layout["width"], layout["height"], layout["fps"]
    audio = layout["keep_audio"]

    cmd = [_ffmpeg(), "-y", "-hide_banner", "-nostdin",
           "-progress", "pipe:1", "-nostats"]
    for seg in segments:
        # Seeking before -i rather than trimming in the filter graph: ffmpeg
        # then only decodes the part that is wanted, which is the difference
        # between reading a whole hour-long capture and reading four seconds
        # of it. The same file can appear repeatedly with different points.
        if seg.start > 0:
            cmd += ["-ss", f"{seg.start:.3f}"]
        if seg.duration > 0 and seg.trimmed:
            cmd += ["-t", f"{seg.duration:.3f}"]
        cmd += ["-i", str(seg.path)]

    parts = []
    for i in range(len(segments)):
        # setpts is what makes a trimmed part safe to concatenate: concat
        # expects every input to start at zero, and a part taken from the middle
        # of a file otherwise arrives carrying the timestamps it had there.
        parts.append(
            f"[{i}:v]setpts=PTS-STARTPTS,fps={fps},"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={background},"
            f"setsar=1,format=rgba[v{i}]")
        if audio:
            # concat refuses audio inputs that disagree on rate or layout just
            # as it refuses mismatched video, so they are levelled here too.
            parts.append(
                f"[{i}:a]asetpts=PTS-STARTPTS,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=stereo[a{i}]")

    labels = "".join(f"[v{i}]" + (f"[a{i}]" if audio else "")
                     for i in range(len(segments)))
    parts.append(f"{labels}concat=n={len(segments)}:v=1:a={1 if audio else 0}"
                 + ("[cat][aout]" if audio else "[cat]"))

    # Both outputs are laid over a solid colour, so the result is opaque.
    # Transparent padding looked tempting for GIF, but GIF resolves a
    # transparent pixel by showing whatever was underneath it — so the bars
    # beside a portrait clip filled with the previous clip's background instead
    # of going blank. Flattening is the only version that joins predictably;
    # letting ffmpeg drop the alpha itself fills with black rather than the
    # colour that was asked for, hence the explicit colour source.
    cmd += ["-f", "lavfi", "-i", f"color=c={background}:s={w}x{h}:r={fps}"]
    parts.append(f"[{len(segments)}:v][cat]overlay=shortest=1,setsar=1[flat]")

    if output == GIF:
        # One palette for the whole join rather than one per part, or the
        # colours shift at every seam.
        parts.append("[flat]split[pal][use]")
        parts.append("[pal]palettegen[p]")
        parts.append("[use][p]paletteuse=dither=bayer:bayer_scale=5[out]")
    else:
        parts.append("[flat]format=yuv420p[out]")

    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]"]
    if audio:
        cmd += ["-map", "[aout]"]

    if output == GIF:
        cmd += ["-loop", "0"]
    else:
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        cmd += ["-c:a", "aac", "-b:a", "160k"] if audio else ["-an"]

    cmd.append(str(output_path))
    return cmd


def concat(segments: Sequence, output_path, *, output: str = MP4,
           size_mode: str = MATCH_FIRST, fps: float = 0.0,
           background: str = "black", crf: int = DEFAULT_CRF,
           preset: str = "medium", max_width: int = 0,
           on_progress: Optional[Callable[[int], None]] = None,
           should_stop: Optional[Callable[[], bool]] = None) -> str:
    """Join the timeline, in the order given, into one file.

    Takes `Segment`s, or bare paths when nothing is trimmed. Returns the path
    written."""
    timeline = as_segments(segments)
    if len(timeline) < 2:
        raise ConcatError("Pick at least two files to join")
    empty = [s.path.name for s in timeline if s.trimmed and s.duration <= 0]
    if empty:
        raise ConcatError("Nothing is left of " + ", ".join(empty[:5]))

    out = Path(output_path)
    resolved = {s.path.resolve() for s in timeline}
    if out.resolve() in resolved:
        raise ConcatError("Refusing to overwrite one of the files being joined")
    out.parent.mkdir(parents=True, exist_ok=True)

    layout = plan(timeline, size_mode=size_mode, fps=fps, max_width=max_width)
    cmd = build_command(timeline, out, layout=layout, output=output,
                        background=background, crf=crf, preset=preset)

    try:
        proc = popen_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True,
                            encoding="utf-8", errors="replace")
    except OSError as e:
        raise ConcatError(f"Could not run ffmpeg: {e}") from e

    total_us = layout["duration"] * 1_000_000
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
            raise ConcatError("Cancelled")
        if on_progress is not None and total_us > 0:
            # Elapsed output time, not frames: the parts run at different rates
            # and a frame counter would jump about between them.
            m = re.search(r"out_time_us=(\d+)", line)
            if m:
                on_progress(min(int(m.group(1)) * 100 // int(total_us), 100))

    proc.wait()
    if proc.returncode != 0 or not out.exists():
        raise ConcatError(
            f"ffmpeg failed (code {proc.returncode}).\n{''.join(log).strip()[-1500:]}")
    if on_progress is not None:
        on_progress(100)
    return str(out)
