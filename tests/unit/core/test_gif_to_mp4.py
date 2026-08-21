"""Unit tests for converting finished animations to video.

The command builder is checked without ffmpeg present; the conversions
themselves are skipped when it is not installed, so the suite still runs on a
machine without it.
"""
import pytest
from PIL import Image

from src.core import gif_to_mp4
from src.core.video_to_gif import VideoConversionError, is_ffmpeg_available

needs_ffmpeg = pytest.mark.skipif(not is_ffmpeg_available(),
                                  reason="ffmpeg is not installed")


@pytest.fixture()
def toy_gif(tmp_path):
    """A short GIF with a transparent border, so alpha handling is exercised."""
    frames = []
    for i in range(6):
        frame = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
        block = Image.new("RGBA", (24, 24), (200, 40 + i * 20, 60, 255))
        frame.paste(block, (4 + i * 4, 8))
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=64))
    out = tmp_path / "toy.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=80,
                   loop=0, transparency=0, disposal=2)
    return out


# ── the command builder ──────────────────────────────────────────────────

@needs_ffmpeg
def test_h264_command_flattens_onto_the_chosen_colour(tmp_path):
    cmd = gif_to_mp4.build_command("in.gif", tmp_path / "out.mp4",
                                   codec=gif_to_mp4.H264, background="#204060")
    joined = " ".join(cmd)
    assert "color=c=#204060" in joined
    assert "overlay=shortest=1" in joined
    assert "libx264" in cmd
    # yuv420p has nowhere to keep alpha and every player understands it.
    assert "yuv420p" in cmd


@needs_ffmpeg
def test_commands_force_even_dimensions(tmp_path):
    """H.264 and VP9 both reject odd width or height in 4:2:0."""
    for codec in gif_to_mp4.CODECS:
        cmd = gif_to_mp4.build_command("in.gif", tmp_path / "o", codec=codec)
        assert "scale=trunc(iw/2)*2:trunc(ih/2)*2" in " ".join(cmd)


@needs_ffmpeg
def test_vp9_command_keeps_the_alpha_channel(tmp_path):
    cmd = gif_to_mp4.build_command("in.gif", tmp_path / "out.webm",
                                   codec=gif_to_mp4.VP9_ALPHA)
    assert "libvpx-vp9" in cmd
    # The alpha has to be declared both on the way into the encoder and out of it.
    assert "format=yuva420p" in cmd[cmd.index("-vf") + 1]
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuva420p"
    # Nothing is composited underneath: that is the whole point of this codec.
    assert "overlay=shortest=1" not in " ".join(cmd)


@needs_ffmpeg
def test_crf_and_resize_reach_the_command(tmp_path):
    cmd = gif_to_mp4.build_command("in.gif", tmp_path / "o.mp4", crf=31, width=640, fps=12)
    assert cmd[cmd.index("-crf") + 1] == "31"
    joined = " ".join(cmd)
    # A width is an upper limit, not a target, so it is expressed with min().
    assert r"min(iw\,640)" in joined
    assert "fps=12" in joined


@needs_ffmpeg
def test_no_width_means_no_scaling_step(tmp_path):
    joined = " ".join(gif_to_mp4.build_command("in.gif", tmp_path / "o.mp4"))
    assert "min(iw" not in joined
    assert "lanczos" not in joined


@needs_ffmpeg
def test_progress_is_asked_for_in_a_parsable_form(tmp_path):
    """Without -progress, ffmpeg's counters arrive carriage-return separated."""
    cmd = gif_to_mp4.build_command("in.gif", tmp_path / "o.mp4")
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"


def test_extension_follows_the_codec():
    assert gif_to_mp4.extension_for(gif_to_mp4.H264) == "mp4"
    assert gif_to_mp4.extension_for(gif_to_mp4.VP9_ALPHA) == "webm"


# ── guards ───────────────────────────────────────────────────────────────

def test_missing_input_is_reported(tmp_path):
    with pytest.raises(VideoConversionError, match="not found"):
        gif_to_mp4.convert_to_video(tmp_path / "nope.gif", tmp_path / "o.mp4")


@needs_ffmpeg
def test_unknown_codec_is_reported(toy_gif, tmp_path):
    with pytest.raises(VideoConversionError, match="Unknown codec"):
        gif_to_mp4.convert_to_video(toy_gif, tmp_path / "o.mp4", codec="AV1")


@needs_ffmpeg
def test_it_refuses_to_write_over_its_own_source(toy_gif):
    with pytest.raises(VideoConversionError, match="overwrite the source"):
        gif_to_mp4.convert_to_video(toy_gif, toy_gif)


# ── real conversions ─────────────────────────────────────────────────────

@needs_ffmpeg
def test_reads_size_and_frame_count(toy_gif):
    info = gif_to_mp4.get_animation_info(toy_gif)
    assert (info["width"], info["height"]) == (64, 48)
    assert info["frames"] == 6


@needs_ffmpeg
def test_converts_to_mp4_and_reports_the_saving(toy_gif, tmp_path):
    out = tmp_path / "out.mp4"
    seen = []
    gif_to_mp4.convert_to_video(toy_gif, out, crf=26, on_progress=seen.append)
    assert out.exists() and out.stat().st_size > 0
    before, after, ratio = gif_to_mp4.size_change(toy_gif, out)
    assert before > 0 and after > 0 and ratio > 0
    assert seen and seen[-1] == 100


@needs_ffmpeg
def test_the_background_colour_actually_lands_in_the_video(toy_gif, tmp_path):
    """The corner of this GIF is transparent, so it shows the chosen colour."""
    import subprocess
    from src.core.video_to_gif import find_ffmpeg

    out = tmp_path / "green.mp4"
    gif_to_mp4.convert_to_video(toy_gif, out, background="#00FF00", crf=18)
    still = tmp_path / "still.png"
    subprocess.run([find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(out), "-vframes", "1", str(still)], check=True)
    r, g, b = Image.open(still).convert("RGB").getpixel((1, 1))
    assert g > 180 and r < 90 and b < 90


@needs_ffmpeg
def test_vp9_keeps_transparency_where_mp4_cannot(toy_gif, tmp_path):
    """Decoding needs libvpx-vp9: VP9 alpha rides in a side stream the
    built-in decoder ignores, which makes it look lost when it is not."""
    import subprocess
    from src.core.video_to_gif import find_ffmpeg

    out = tmp_path / "alpha.webm"
    gif_to_mp4.convert_to_video(toy_gif, out, codec=gif_to_mp4.VP9_ALPHA, crf=26)
    still = tmp_path / "alpha.png"
    subprocess.run([find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-c:v", "libvpx-vp9", "-i", str(out), "-vframes", "1",
                    "-vf", "format=rgba", str(still)], check=True)
    assert Image.open(still).convert("RGBA").getpixel((1, 1))[3] == 0


@needs_ffmpeg
def test_output_defaults_to_the_source_name(toy_gif):
    produced = gif_to_mp4.convert_to_video(toy_gif, crf=30)
    assert produced.endswith(".mp4")
    assert toy_gif.with_suffix(".mp4").exists()


@needs_ffmpeg
def test_a_width_limit_never_enlarges_a_smaller_file(toy_gif, tmp_path):
    """Blowing a 64px source up to 800 would cost bitrate and add only blur."""
    out = tmp_path / "capped.mp4"
    gif_to_mp4.convert_to_video(toy_gif, out, width=800, crf=30)
    assert gif_to_mp4.get_animation_info(out)["width"] == 64


@needs_ffmpeg
def test_a_width_limit_does_shrink_a_larger_file(toy_gif, tmp_path):
    out = tmp_path / "shrunk.mp4"
    gif_to_mp4.convert_to_video(toy_gif, out, width=32, crf=30)
    info = gif_to_mp4.get_animation_info(out)
    assert info["width"] == 32
    assert info["height"] == 24          # 64x48 keeps its 4:3


@needs_ffmpeg
def test_without_a_limit_the_source_size_is_kept(toy_gif, tmp_path):
    out = tmp_path / "same.mp4"
    gif_to_mp4.convert_to_video(toy_gif, out, crf=30)
    info = gif_to_mp4.get_animation_info(out)
    assert (info["width"], info["height"]) == (64, 48)


# ── aspect ratio ─────────────────────────────────────────────────────────

@needs_ffmpeg
def test_both_paths_pin_the_pixel_aspect(tmp_path):
    """Guards the bug where output was tagged 4:3 and players squashed it."""
    for codec in gif_to_mp4.CODECS:
        cmd = gif_to_mp4.build_command("in.gif", tmp_path / "o", codec=codec)
        assert "setsar=1" in " ".join(cmd)


@pytest.fixture()
def tall_gif(tmp_path):
    """Portrait, so a wrongly-declared 4:3 aspect would be obvious."""
    frames = []
    for i in range(4):
        frame = Image.new("RGB", (64, 128), (20, 20, 20))
        frame.paste(Image.new("RGB", (20, 20), (220, 60 + i * 30, 40)), (10, 10 + i * 8))
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=32))
    out = tmp_path / "tall.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=80, loop=0)
    return out


@needs_ffmpeg
def test_the_output_declares_square_pixels(tall_gif, tmp_path):
    """scale2ref carries the colour source's 4:3 aspect over unless it is pinned.

    The stored size stayed right, so only checking width and height missed this:
    the file said 'display me as 4:3' and players obliged."""
    for codec in gif_to_mp4.CODECS:
        out = tmp_path / f"a.{gif_to_mp4.extension_for(codec)}"
        gif_to_mp4.convert_to_video(tall_gif, out, codec=codec, crf=30)
        info = gif_to_mp4.get_animation_info(out)
        assert info["sar"] == "1:1", f"{codec} tagged the pixels {info['sar']}"
        assert (info["width"], info["height"]) == (64, 128)


@needs_ffmpeg
def test_the_displayed_shape_matches_the_source(tall_gif, tmp_path):
    """Stored size times pixel aspect has to come back to the source's shape."""
    out = tmp_path / "shape.mp4"
    gif_to_mp4.convert_to_video(tall_gif, out, crf=30)
    info = gif_to_mp4.get_animation_info(out)
    num, _, den = info["sar"].partition(":")
    displayed = info["width"] * (int(num) / int(den))
    assert displayed / info["height"] == pytest.approx(64 / 128, rel=0.01)
