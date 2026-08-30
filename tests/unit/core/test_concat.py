import pytest
from PIL import Image, ImageDraw, ImageSequence

from src.core import concat
from src.core.video_to_gif import is_ffmpeg_available

needs_ffmpeg = pytest.mark.skipif(not is_ffmpeg_available(),
                                  reason="ffmpeg is not installed")


def _seg(w=160, h=120, *, fps=10.0, duration=1.0, audio=False,
         name="a.gif", start=0.0, end=0.0):
    """A segment with its probe results supplied, so no ffprobe run is needed."""
    return concat.Segment(name, start=start, end=end,
                          info={"width": w, "height": h, "fps": fps,
                                "duration": duration, "has_audio": audio,
                                "sar": "1:1"})


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


def _ramp_gif(path, frames=10, size=(120, 80)):
    """Frame i is a distinct grey, so which part of the clip survived a trim can
    be read straight off the pixels."""
    images = [Image.new("RGB", size, (i * 25, i * 25, i * 25)) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=100, loop=0)
    return path


# ── segments ─────────────────────────────────────────────────────────────

def test_an_untrimmed_segment_is_the_whole_clip():
    s = _seg(duration=4.0)
    assert s.duration == 4.0
    assert s.trimmed is False
    assert s.label() == "a.gif"


def test_an_end_of_zero_means_run_to_the_end():
    """So a freshly added segment is valid before anything has been probed."""
    s = _seg(duration=4.0, start=1.0)
    assert s.out_point == 4.0
    assert s.duration == 3.0


def test_trimming_both_ends():
    s = _seg(duration=4.0, start=1.0, end=3.0)
    assert s.duration == 2.0
    assert s.trimmed is True
    assert "1.00s" in s.label() and "3.00s" in s.label()


def test_an_out_point_past_the_end_is_clamped():
    assert _seg(duration=2.0, end=9.0).duration == 2.0


def test_a_segment_cannot_have_negative_length():
    assert _seg(duration=4.0, start=3.0, end=1.0).duration == 0.0


# ── plan ─────────────────────────────────────────────────────────────────

def test_the_first_file_sets_the_frame_by_default():
    layout = concat.plan([_seg(160, 120), _seg(320, 240)])
    assert (layout["width"], layout["height"]) == (160, 120)


def test_fitting_the_largest_takes_the_widest_and_the_tallest():
    """Not the largest single file — a wide clip and a tall one both have to fit."""
    layout = concat.plan([_seg(320, 100), _seg(100, 400)],
                         size_mode=concat.MATCH_LARGEST)
    assert (layout["width"], layout["height"]) == (320, 400)


def test_dimensions_come_out_even():
    """4:2:0 chroma cannot describe an odd width, and H.264 refuses one."""
    layout = concat.plan([_seg(161, 121)])
    assert layout["width"] % 2 == 0 and layout["height"] % 2 == 0


def test_the_frame_rate_levels_up_not_down():
    """Matching the worst clip would throw away motion the others recorded."""
    layout = concat.plan([_seg(fps=10), _seg(fps=30)])
    assert layout["fps"] == 30


def test_an_explicit_frame_rate_wins():
    assert concat.plan([_seg(fps=30)], fps=12)["fps"] == 12


def test_sound_survives_only_when_every_clip_has_some():
    both = concat.plan([_seg(audio=True), _seg(audio=True)])
    mixed = concat.plan([_seg(audio=True), _seg(audio=False)])
    assert both["keep_audio"] is True
    # Concatenating a silent clip against one with audio drifts out of sync from
    # the seam onwards, so the honest choice is all or nothing.
    assert mixed["keep_audio"] is False


def test_it_reports_which_clips_will_be_padded():
    layout = concat.plan([_seg(160, 120), _seg(100, 200), _seg(160, 120)])
    assert layout["padded"] == [False, True, False]


def test_the_planned_length_counts_trims_not_sources():
    """The progress bar measures against this, and so does the summary."""
    layout = concat.plan([_seg(duration=10.0, start=8.0),      # 2s
                          _seg(duration=10.0, end=1.5)])       # 1.5s
    assert layout["duration"] == pytest.approx(3.5)


def test_a_width_cap_only_ever_shrinks():
    """The preview render leans on this; blowing a clip up would cost bitrate
    and add blur without adding detail the source never had."""
    small = concat.plan([_seg(320, 240)], max_width=1920)
    assert (small["width"], small["height"]) == (320, 240)


def test_a_width_cap_keeps_the_shape():
    capped = concat.plan([_seg(1920, 1080)], max_width=640)
    assert capped["width"] == 640
    assert capped["height"] == pytest.approx(360, abs=2)


def test_a_capped_frame_is_still_even():
    """Odd dimensions survive neither H.264 nor the rounding on the way down."""
    capped = concat.plan([_seg(1080, 1921)], max_width=641)
    assert capped["width"] % 2 == 0 and capped["height"] % 2 == 0


def test_unreadable_input_is_refused_rather_than_guessed_at():
    with pytest.raises(concat.ConcatError, match="None of these files"):
        concat.plan([concat.Segment("x.gif", info={"width": 0, "height": 0})])


# ── build_command ────────────────────────────────────────────────────────

def _chain(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def _command(segments, out="out.mp4", **kw):
    layout = kw.pop("layout", None) or concat.plan(segments)
    return concat.build_command(segments, out, layout=layout, **kw)


@needs_ffmpeg
def test_every_input_is_normalised_before_being_joined():
    cmd = _command([_seg(name="a.gif"), _seg(name="b.mp4"), _seg(name="c.webm")])
    chain = _chain(cmd)
    for i in range(3):
        assert f"[{i}:v]" in chain and f"[v{i}]" in chain
    assert "concat=n=3:v=1" in chain


@needs_ffmpeg
def test_clips_are_fitted_and_padded_never_stretched():
    chain = _chain(_command([_seg(), _seg()]))
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=160:120" in chain


@needs_ffmpeg
def test_square_pixels_are_forced_on_every_part():
    """One part claiming non-square pixels plays the whole join back squashed."""
    assert _chain(_command([_seg(), _seg()])).count("setsar=1") >= 2


@needs_ffmpeg
def test_a_trimmed_segment_seeks_before_it_decodes():
    """Seeking in the filter graph would decode the whole file to throw it away."""
    cmd = _command([_seg(duration=60.0, start=10.0, end=14.0), _seg()])
    assert "-ss" in cmd and cmd[cmd.index("-ss") + 1] == "10.000"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "4.000"


@needs_ffmpeg
def test_an_untrimmed_segment_seeks_nowhere():
    assert "-ss" not in _command([_seg(), _seg()])


@needs_ffmpeg
def test_a_trimmed_part_is_rebased_to_zero():
    """concat expects every input at zero; a slice from the middle of a file
    otherwise arrives carrying the timestamps it had there."""
    assert "setpts=PTS-STARTPTS" in _chain(_command([_seg(start=1.0), _seg()]))


@needs_ffmpeg
def test_the_same_file_can_appear_twice_with_different_points():
    segs = [_seg(name="clip.mp4", duration=10.0, end=2.0),
            _seg(name="clip.mp4", duration=10.0, start=8.0)]
    cmd = _command(segs)
    assert cmd.count("clip.mp4") == 2, "each use needs its own input"
    assert "concat=n=2" in _chain(cmd)


@needs_ffmpeg
def test_the_gif_path_builds_one_palette_for_the_whole_join():
    cmd = _command([_seg(), _seg()], "out.gif", output=concat.GIF)
    chain = _chain(cmd)
    assert "palettegen" in chain and "paletteuse" in chain
    # A palette per part would shift the colours at every seam.
    assert chain.count("palettegen") == 1
    assert "-loop" in cmd


@needs_ffmpeg
def test_the_mp4_path_encodes_h264():
    cmd = _command([_seg(), _seg()], output=concat.MP4)
    assert "libx264" in cmd
    assert "yuv420p" in _chain(cmd)


@needs_ffmpeg
def test_both_outputs_are_laid_over_a_solid_colour():
    """GIF resolves transparency by showing what was underneath, so padding a
    portrait clip with alpha filled the bars with the previous clip."""
    for output in (concat.MP4, concat.GIF):
        cmd = _command([_seg(), _seg()], "out", output=output, background="white")
        assert "color=c=white" in " ".join(cmd)
        assert "overlay=shortest=1" in _chain(cmd)


@needs_ffmpeg
def test_audio_is_mapped_and_levelled_only_when_it_is_being_kept():
    quiet = _command([_seg(), _seg()])
    assert "-an" in quiet
    assert "[aout]" not in " ".join(quiet)

    loud = _command([_seg(audio=True), _seg(audio=True)])
    assert "[aout]" in " ".join(loud)
    assert "aac" in loud
    # concat refuses audio that disagrees on rate or layout just as it refuses
    # mismatched video.
    assert "aformat=" in _chain(loud)


# ── guards ───────────────────────────────────────────────────────────────

def test_one_clip_is_not_a_join(tmp_path):
    with pytest.raises(concat.ConcatError, match="at least two"):
        concat.concat([_seg()], tmp_path / "out.mp4")


def test_a_segment_trimmed_to_nothing_is_refused(tmp_path):
    with pytest.raises(concat.ConcatError, match="Nothing is left"):
        concat.concat([_seg(duration=4.0, start=2.0, end=2.0), _seg()],
                      tmp_path / "out.mp4")


def test_it_will_not_write_over_one_of_its_own_inputs(tmp_path):
    a, b = tmp_path / "a.gif", tmp_path / "b.gif"
    _make_gif(a)
    _make_gif(b)
    with pytest.raises(concat.ConcatError, match="Refusing"):
        concat.concat([a, b], a)


def test_bare_paths_still_work_for_the_untrimmed_case(tmp_path):
    a = _make_gif(tmp_path / "a.gif")
    segments = concat.as_segments([a, a])
    assert all(isinstance(s, concat.Segment) for s in segments)
    assert not segments[0].trimmed


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
def test_a_trim_actually_removes_that_part_of_the_clip(tmp_path):
    """Reading the grey ramp back says which half of the source survived."""
    ramp = _ramp_gif(tmp_path / "ramp.gif")            # 1.00s, greys 0..225
    other = _make_gif(tmp_path / "other.gif", size=(120, 80), rgb=(0, 200, 0))

    head_gone = concat.Segment(ramp, start=0.5)
    out = tmp_path / "trimmed.gif"
    concat.concat([head_gone, concat.Segment(other)], out, output=concat.GIF)

    assert concat.probe(out)["duration"] == pytest.approx(
        head_gone.duration + 1.0, abs=0.15)

    greys = [f.convert("RGB").getpixel((60, 40))[0]
             for f in ImageSequence.Iterator(Image.open(out))]
    # The first half of the ramp is grey 0..100. The green clip reads 0 on the
    # red channel, so only values strictly between say the ramp's own range
    # would betray an untrimmed head.
    assert not [g for g in greys if 0 < g < 100], \
        f"the trimmed-off head is still in the join: {greys}"
    assert [g for g in greys if g >= 100], "the kept tail is missing"


@needs_ffmpeg
def test_one_source_used_twice_at_different_points(tmp_path):
    ramp = _ramp_gif(tmp_path / "ramp.gif")
    head = concat.Segment(ramp, end=0.3)
    tail = concat.Segment(ramp, start=0.7)
    out = tmp_path / "bookends.mp4"
    concat.concat([head, tail], out)
    assert concat.probe(out)["duration"] == pytest.approx(
        head.duration + tail.duration, abs=0.15)


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
