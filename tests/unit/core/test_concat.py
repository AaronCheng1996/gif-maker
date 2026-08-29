import pytest
from PIL import Image, ImageDraw, ImageSequence

from src.core import concat
from src.core.video_to_gif import is_ffmpeg_available

needs_ffmpeg = pytest.mark.skipif(not is_ffmpeg_available(),
                                  reason="ffmpeg is not installed")


def _info(w, h, fps=10.0, duration=1.0, audio=False):
    return {"width": w, "height": h, "fps": fps, "duration": duration,
            "has_audio": audio, "sar": "1:1"}


def _make_gif(path, size=(160, 120), frames=10, rgb=(200, 40, 40)):
    """Frames that differ, or the encoder merges them and the file is not what
    the test thinks it is — a solid-colour clip collapses to a single frame."""
    images = []
    for i in range(frames):
        im = Image.new("RGB", size, rgb)
        ImageDraw.Draw(im).rectangle([i * 3, 0, i * 3 + 4, 4], fill=(255, 255, 255))
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=100, loop=0)
    return path


# ── plan ─────────────────────────────────────────────────────────────────

def test_the_first_file_sets_the_frame_by_default():
    layout = concat.plan([_info(160, 120), _info(320, 240)])
    assert (layout["width"], layout["height"]) == (160, 120)


def test_fitting_the_largest_takes_the_widest_and_the_tallest():
    """Not the largest single file — a wide clip and a tall one both have to fit."""
    layout = concat.plan([_info(320, 100), _info(100, 400)],
                         size_mode=concat.MATCH_LARGEST)
    assert (layout["width"], layout["height"]) == (320, 400)


def test_dimensions_come_out_even():
    """4:2:0 chroma cannot describe an odd width, and H.264 refuses one."""
    layout = concat.plan([_info(161, 121)])
    assert layout["width"] % 2 == 0 and layout["height"] % 2 == 0


def test_the_frame_rate_levels_up_not_down():
    """Matching the worst clip would throw away motion the others recorded."""
    layout = concat.plan([_info(160, 120, fps=10), _info(160, 120, fps=30)])
    assert layout["fps"] == 30


def test_an_explicit_frame_rate_wins():
    layout = concat.plan([_info(160, 120, fps=30)], fps=12)
    assert layout["fps"] == 12


def test_sound_survives_only_when_every_clip_has_some():
    both = concat.plan([_info(8, 8, audio=True), _info(8, 8, audio=True)])
    mixed = concat.plan([_info(8, 8, audio=True), _info(8, 8, audio=False)])
    assert both["keep_audio"] is True
    # Concatenating a silent clip against one with audio drifts out of sync from
    # the seam onwards, so the honest choice is all or nothing.
    assert mixed["keep_audio"] is False


def test_it_reports_which_clips_will_be_padded():
    layout = concat.plan([_info(160, 120), _info(100, 200), _info(160, 120)])
    assert layout["padded"] == [False, True, False]


def test_duration_is_the_sum_of_the_parts():
    layout = concat.plan([_info(8, 8, duration=1.5), _info(8, 8, duration=2.0)])
    assert layout["duration"] == pytest.approx(3.5)


def test_unreadable_input_is_refused_rather_than_guessed_at():
    with pytest.raises(concat.ConcatError, match="None of these files"):
        concat.plan([{"width": 0, "height": 0}])


# ── build_command ────────────────────────────────────────────────────────

def _command(paths, out, **kw):
    layout = kw.pop("layout", None) or concat.plan([_info(160, 120)] * len(paths))
    return concat.build_command(paths, out, layout=layout, **kw)


@needs_ffmpeg
def test_every_input_is_normalised_before_being_joined():
    cmd = _command(["a.gif", "b.mp4", "c.webm"], "out.mp4")
    chain = cmd[cmd.index("-filter_complex") + 1]
    for i in range(3):
        assert f"[{i}:v]fps=" in chain
        assert f"[v{i}]" in chain
    assert "concat=n=3:v=1" in chain


@needs_ffmpeg
def test_clips_are_fitted_and_padded_never_stretched():
    chain = _command(["a.gif", "b.gif"], "out.mp4")[
        _command(["a.gif", "b.gif"], "out.mp4").index("-filter_complex") + 1]
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=160:120" in chain


@needs_ffmpeg
def test_square_pixels_are_forced_on_every_part():
    """One part claiming non-square pixels plays the whole join back squashed."""
    chain = _command(["a.gif", "b.gif"], "out.mp4")[
        _command(["a.gif", "b.gif"], "out.mp4").index("-filter_complex") + 1]
    assert chain.count("setsar=1") >= 2


@needs_ffmpeg
def test_the_gif_path_builds_one_palette_for_the_whole_join():
    cmd = _command(["a.gif", "b.gif"], "out.gif", output=concat.GIF)
    chain = cmd[cmd.index("-filter_complex") + 1]
    assert "palettegen" in chain and "paletteuse" in chain
    # A palette per part would shift the colours at every seam.
    assert chain.count("palettegen") == 1
    assert "-loop" in cmd


@needs_ffmpeg
def test_the_mp4_path_encodes_h264():
    cmd = _command(["a.gif", "b.gif"], "out.mp4", output=concat.MP4)
    assert "libx264" in cmd
    assert "yuv420p" in cmd[cmd.index("-filter_complex") + 1]


@needs_ffmpeg
def test_both_outputs_are_laid_over_a_solid_colour():
    """GIF resolves transparency by showing what was underneath, so padding a
    portrait clip with alpha filled the bars with the previous clip."""
    for output in (concat.MP4, concat.GIF):
        cmd = _command(["a.gif", "b.gif"], "out", output=output, background="white")
        assert "color=c=white" in " ".join(cmd)
        assert "overlay=shortest=1" in cmd[cmd.index("-filter_complex") + 1]


@needs_ffmpeg
def test_audio_is_mapped_only_when_it_is_being_kept():
    silent = concat.plan([_info(8, 8), _info(8, 8)])
    loud = concat.plan([_info(8, 8, audio=True), _info(8, 8, audio=True)])

    quiet_cmd = _command(["a", "b"], "out.mp4", layout=silent)
    assert "-an" in quiet_cmd
    assert "[aout]" not in " ".join(quiet_cmd)

    loud_cmd = _command(["a", "b"], "out.mp4", layout=loud)
    assert "[aout]" in " ".join(loud_cmd)
    assert "aac" in loud_cmd


# ── guards ───────────────────────────────────────────────────────────────

def test_one_clip_is_not_a_join(tmp_path):
    with pytest.raises(concat.ConcatError, match="at least two"):
        concat.concat([tmp_path / "a.gif"], tmp_path / "out.mp4")


def test_it_will_not_write_over_one_of_its_own_inputs(tmp_path):
    a, b = tmp_path / "a.gif", tmp_path / "b.gif"
    _make_gif(a)
    _make_gif(b)
    with pytest.raises(concat.ConcatError, match="Refusing"):
        concat.concat([a, b], a)


# ── the real thing ───────────────────────────────────────────────────────

@needs_ffmpeg
def test_the_join_lasts_as_long_as_its_parts_together(tmp_path):
    a = _make_gif(tmp_path / "a.gif", size=(160, 120))
    b = _make_gif(tmp_path / "b.gif", size=(160, 120), rgb=(40, 40, 200))
    out = tmp_path / "joined.mp4"
    concat.concat([a, b], out)

    parts = sum(concat.probe(p)["duration"] for p in (a, b))
    joined = concat.probe(out)
    assert joined["duration"] == pytest.approx(parts, abs=0.15)
    assert (joined["width"], joined["height"]) == (160, 120)
    assert joined["sar"] == "1:1"


@needs_ffmpeg
def test_a_differently_shaped_clip_is_letterboxed_not_distorted(tmp_path):
    """The one thing a join must never do is change what a clip looks like."""
    wide = _make_gif(tmp_path / "wide.gif", size=(160, 120), rgb=(255, 0, 0))
    tall = _make_gif(tmp_path / "tall.gif", size=(100, 200), rgb=(0, 255, 0))
    out = tmp_path / "joined.gif"
    concat.concat([wide, tall], out, output=concat.GIF, background="black")

    frames = [f.convert("RGB") for f in ImageSequence.Iterator(Image.open(out))]
    green = frames[len(frames) * 3 // 4]          # well inside the second clip
    w, h = green.size
    row = [green.getpixel((x, h // 2)) for x in range(w)]
    xs = [x for x, px in enumerate(row) if px[1] > 120 and px[0] < 120]
    assert xs, "the second clip never appears in the join"

    content = max(xs) - min(xs) + 1
    fitted = round(100 * (120 / 200))             # 100x200 fitted into 160x120
    assert content == pytest.approx(fitted, abs=2), \
        f"content is {content}px wide; {w} would mean it was stretched"
    assert abs(min(xs) - (w - 1 - max(xs))) <= 2, "bars are not centred"

    # The bars must be the padding colour, not whatever the last clip left behind.
    assert green.getpixel((2, h // 2)) == pytest.approx((0, 0, 0), abs=12)


@needs_ffmpeg
def test_a_gif_and_a_video_join_into_one_file(tmp_path):
    from src.core import gif_to_mp4
    gif = _make_gif(tmp_path / "a.gif", size=(160, 120))
    seed = _make_gif(tmp_path / "seed.gif", size=(320, 180), rgb=(20, 90, 20))
    mp4 = tmp_path / "b.mp4"
    gif_to_mp4.convert_to_video(seed, mp4, crf=30)

    out = tmp_path / "mixed.mp4"
    concat.concat([gif, mp4], out)
    joined = concat.probe(out)
    assert joined["width"] and joined["duration"] > 0
    assert joined["sar"] == "1:1"
