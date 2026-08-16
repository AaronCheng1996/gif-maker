"""Unit tests for the Spine atlas parser (4.1 and legacy formats)."""
import pytest

from src.core.spine.atlas import Atlas

ATLAS_41 = """skeleton.png
size: 1024, 512
filter: Linear, Linear
head
bounds: 10, 20, 100, 200
rotated_part
bounds: 200, 40, 30, 60
rotate: 270
trimmed
bounds: 300, 50, 40, 30
offsets: 5, 8, 60, 50

second.png
size: 256, 256
extra
bounds: 1, 2, 3, 4
"""

ATLAS_LEGACY = """skeleton.png
size: 1024,512
format: RGBA8888
filter: Linear,Linear
repeat: none
head
  rotate: false
  xy: 10, 20
  size: 100, 200
  orig: 110, 210
  offset: 5, 4
  index: -1
spun
  rotate: true
  xy: 200, 40
  size: 30, 60
  orig: 30, 60
  offset: 0, 0
  index: -1
"""


def test_parses_41_pages_and_regions():
    atlas = Atlas.parse_text(ATLAS_41)
    assert [p.name for p in atlas.pages] == ["skeleton.png", "second.png"]
    assert atlas.pages[0].width == 1024 and atlas.pages[0].height == 512
    assert set(atlas.regions) == {"head", "rotated_part", "trimmed", "extra"}


def test_41_bounds_and_defaults():
    atlas = Atlas.parse_text(ATLAS_41)
    head = atlas.find_region("head")
    assert (head.x, head.y, head.width, head.height) == (10, 20, 100, 200)
    assert head.degrees == 0
    # No offsets line -> nothing was trimmed.
    assert (head.original_width, head.original_height) == (100, 200)
    assert (head.offset_x, head.offset_y) == (0, 0)


def test_41_rotated_region_records_unrotated_size():
    """`bounds` gives the source size before rotation; the page footprint is swapped.

    Reading it the other way round pushes real regions past the page edge, and
    makes Spine's UV maths sample the wrong part of the atlas."""
    atlas = Atlas.parse_text(ATLAS_41)
    r = atlas.find_region("rotated_part")
    assert r.degrees == 270
    assert (r.width, r.height) == (30, 60)                     # un-rotated source
    assert (r.original_width, r.original_height) == (30, 60)   # nothing trimmed
    assert (r.packed_width, r.packed_height) == (60, 30)       # swapped on the page


def test_unrotated_region_footprint_matches_its_size():
    atlas = Atlas.parse_text(ATLAS_41)
    r = atlas.find_region("head")
    assert (r.packed_width, r.packed_height) == (r.width, r.height)


def test_rotated_regions_stay_inside_the_page():
    """A packed atlas never places a region past the page edge; this is what
    distinguishes the two possible readings of `bounds` for rotated regions."""
    atlas = Atlas.parse_text(ATLAS_41)
    for r in atlas.regions.values():
        assert r.x + r.packed_width <= r.page.width
        assert r.y + r.packed_height <= r.page.height


def test_41_offsets_record_trimming():
    atlas = Atlas.parse_text(ATLAS_41)
    r = atlas.find_region("trimmed")
    assert (r.offset_x, r.offset_y) == (5, 8)
    assert (r.original_width, r.original_height) == (60, 50)
    assert (r.width, r.height) == (40, 30)


def test_region_belongs_to_its_page():
    atlas = Atlas.parse_text(ATLAS_41)
    assert atlas.find_region("head").page.name == "skeleton.png"
    assert atlas.find_region("extra").page.name == "second.png"


def test_parses_legacy_format():
    atlas = Atlas.parse_text(ATLAS_LEGACY)
    head = atlas.find_region("head")
    assert (head.x, head.y) == (10, 20)
    assert (head.width, head.height) == (100, 200)
    assert (head.original_width, head.original_height) == (110, 210)
    assert (head.offset_x, head.offset_y) == (5, 4)
    assert head.degrees == 0


def test_legacy_rotate_true_means_90_degrees():
    atlas = Atlas.parse_text(ATLAS_LEGACY)
    assert atlas.find_region("spun").degrees == 90


def test_missing_bounds_raises():
    with pytest.raises(ValueError):
        Atlas.parse_text("page.png\nsize: 10, 10\nbroken\nrotate: false\n")


def test_find_region_returns_none_for_unknown():
    atlas = Atlas.parse_text(ATLAS_41)
    assert atlas.find_region("nope") is None


ATLAS_PMA = """page.png
size: 64, 64
filter: Linear, Linear
pma: true
blob
bounds: 0, 0, 16, 16
"""


def test_pma_flag_is_read_off_the_page():
    atlas = Atlas.parse_text(ATLAS_PMA)
    assert atlas.pages[0].pma is True
    assert atlas.premultiplied is True


def test_atlas_without_the_flag_is_straight_alpha():
    assert Atlas.parse_text(ATLAS_41).premultiplied is False
    assert all(page.pma is False for page in Atlas.parse_text(ATLAS_41).pages)


def test_premultiplied_is_true_when_any_page_declares_it():
    mixed = ATLAS_41 + "\nthird.png\nsize: 32, 32\npma: true\nbit\nbounds: 0, 0, 4, 4\n"
    assert Atlas.parse_text(mixed).premultiplied is True
