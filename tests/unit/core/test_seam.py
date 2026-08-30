import pytest
from PIL import Image, ImageDraw

from src.core import seam


def _frame(i, n=60, size=(160, 120)):
    """A ball travelling left to right over a slowly shifting background."""
    w, h = size
    im = Image.new("RGB", size, (20, 20 + i, 60))
    d = ImageDraw.Draw(im)
    x = 8 + (w - 24) * i / (n - 1)
    d.ellipse([x, h / 2 - 10, x + 16, h / 2 + 6], fill=(240, 190, 60))
    d.rectangle([0, h - 12, w, h], fill=(90, 90, 90))
    return im


@pytest.fixture(scope="module")
def clip():
    return [_frame(i) for i in range(60)]


# ── distance ─────────────────────────────────────────────────────────────

def test_a_frame_against_itself_is_zero(clip):
    sig = seam.signature(clip[10])
    assert seam.distance(sig, sig) == pytest.approx(0.0, abs=1e-9)


def test_further_apart_scores_worse(clip):
    sig = seam.signature(clip[30])
    near = seam.distance(sig, seam.signature(clip[31]))
    far = seam.distance(sig, seam.signature(clip[45]))
    other = seam.distance(sig, seam.signature(
        Image.new("RGB", (160, 120), (200, 30, 30))))
    assert near < far < other


def test_motion_running_the_other_way_is_penalised():
    """Two frames can match exactly and still jar, if one is mid-pan and the
    other is travelling back the way it came."""
    base = Image.new("RGB", (160, 120), (30, 40, 60))
    ImageDraw.Draw(base).ellipse([70, 50, 86, 66], fill=(240, 190, 60))
    left = base.copy()
    ImageDraw.Draw(left).ellipse([60, 50, 76, 66], fill=(240, 190, 60))
    right = base.copy()
    ImageDraw.Draw(right).ellipse([80, 50, 96, 66], fill=(240, 190, 60))

    here = seam.signature(base)
    onward, backward = seam.signature(right), seam.signature(left)
    continuing = seam.distance(here, here, onward, onward)
    reversing = seam.distance(here, here, onward, backward)
    assert reversing > continuing


def test_without_neighbours_the_remaining_terms_carry_the_whole_score(clip):
    """Otherwise a still would be flattered by a component that never ran."""
    a, b = seam.signature(clip[0]), seam.signature(clip[40])
    no_motion = seam.distance(a, b)
    with_motion = seam.distance(a, b, seam.signature(clip[1]),
                                seam.signature(clip[41]))
    assert no_motion > 0 and with_motion > 0
    # Not equal, but the same order of magnitude — the reweighting keeps the
    # two comparable rather than making a still look artificially good.
    assert 0.3 < (with_motion / no_motion) < 3.0


# ── find_match ───────────────────────────────────────────────────────────

def test_it_finds_where_the_clip_carries_on(clip):
    """The honest case: the incoming clip really does contain the continuation."""
    best, score = seam.find_match(clip[29], clip, target_next=clip[28])
    assert best in (28, 29, 30)
    assert score <= seam.SEAMLESS
    assert seam.describe(score) == "seamless"


def test_an_unrelated_clip_is_not_called_a_match(clip):
    flat = [Image.new("RGB", (160, 120), (200, 30, 30)) for _ in range(10)]
    _best, score = seam.find_match(clip[29], flat)
    assert seam.describe(score) == "no good match"


def test_the_search_can_be_confined(clip):
    """Which is how the caller stops an in point landing past the out point."""
    best, _score = seam.find_match(clip[29], clip, search=range(40, 60))
    assert best is not None and 40 <= best < 60


def test_an_out_of_range_search_finds_nothing(clip):
    assert seam.find_match(clip[0], clip, search=range(500, 600)) == (None,
                                                                      float("inf"))


def test_nothing_to_search_is_not_an_error(clip):
    assert seam.find_match(clip[0], []) == (None, float("inf"))


# ── describe ─────────────────────────────────────────────────────────────

def test_the_words_follow_the_thresholds():
    assert seam.describe(0.0) == "seamless"
    assert seam.describe(seam.SEAMLESS) == "seamless"
    assert seam.describe(seam.SEAMLESS + 1e-6) == "close"
    assert seam.describe(seam.CLOSE) == "close"
    assert seam.describe(seam.CLOSE + 1e-6) == "no good match"


def test_the_thresholds_separate_a_shot_from_a_scene_change(clip):
    """Guards the calibration: frames from one shot must never score as far
    apart as two different scenes."""
    sig = seam.signature(clip[30])
    within_shot = seam.distance(sig, seam.signature(clip[50]))
    scene_change = seam.distance(sig, seam.signature(
        Image.new("RGB", (160, 120), (200, 30, 30))))
    assert within_shot <= seam.CLOSE < scene_change
