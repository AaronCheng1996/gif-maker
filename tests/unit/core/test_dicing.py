"""Unit tests for rebuilding diced texture atlases.

Both fixtures work the same way round: build a picture, dice it into cells the
way an engine would, shuffle the cells into a sheet, and check that the rebuild
puts the original back.
"""
import base64
import json
import math
import struct

import numpy as np
import pytest
from PIL import Image

from src.core import dicing


def _picture(width, height, seed=0):
    """Something with structure, so a wrong reassembly cannot pass unnoticed."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width]
    r = (x * 255 // max(width - 1, 1)).astype(np.uint8)
    g = (y * 255 // max(height - 1, 1)).astype(np.uint8)
    b = ((x // 7 + y // 5) * 37 % 256).astype(np.uint8)
    a = np.full((height, width), 255, np.uint8)
    noise = rng.integers(0, 12, size=(height, width), dtype=np.uint8)
    return Image.fromarray(np.dstack([r, g + noise, b, a]), "RGBA")


# ── Utage ────────────────────────────────────────────────────────────────

def _dice_utage(picture, cell_size, padding, atlas_cols, shuffle_seed=1):
    """Pack a picture's cells into a sheet in a deliberately jumbled order."""
    step = cell_size - 2 * padding
    w, h = picture.size
    cols, rows = math.ceil(w / step), math.ceil(h / step)
    src = np.asarray(picture)[::-1]                      # work bottom-up

    order = list(range(cols * rows))
    np.random.default_rng(shuffle_seed).shuffle(order)

    atlas_rows = math.ceil(len(order) / atlas_cols)
    atlas = np.zeros((atlas_rows * cell_size, atlas_cols * cell_size, 4), np.uint8)
    cells = [0] * (cols * rows)
    for slot, grid_pos in enumerate(order):
        i, j = divmod(grid_pos, cols)
        y0, y1 = i * step, min(i * step + step, h)
        x0, x1 = j * step, min(j * step + step, w)
        ax = (slot % atlas_cols) * cell_size + padding
        ay = (slot // atlas_cols) * cell_size + padding
        atlas[ay:ay + (y1 - y0), ax:ax + (x1 - x0)] = src[y0:y1, x0:x1]
        cells[grid_pos] = slot
    return Image.fromarray(atlas[::-1], "RGBA"), cells


def test_utage_rebuild_restores_the_original():
    picture = _picture(300, 200)
    atlas, cells = _dice_utage(picture, 64, 3, atlas_cols=8)
    image = dicing.DicedImage("toy", 300, 200, "sheet", cells=cells)

    rebuilt = dicing.rebuild_utage(image, atlas, 64, 3)
    assert rebuilt.size == picture.size
    assert np.array_equal(np.asarray(rebuilt), np.asarray(picture))


def test_utage_rebuild_works_without_padding():
    picture = _picture(128, 128, seed=3)
    atlas, cells = _dice_utage(picture, 64, 0, atlas_cols=2)
    image = dicing.DicedImage("toy", 128, 128, "sheet", cells=cells)
    assert np.array_equal(np.asarray(dicing.rebuild_utage(image, atlas, 64, 0)),
                          np.asarray(picture))


def test_utage_rebuild_rejects_a_cell_list_of_the_wrong_length():
    image = dicing.DicedImage("toy", 300, 200, "sheet", cells=[0, 1, 2])
    with pytest.raises(dicing.DicingError, match="cells but a"):
        dicing.rebuild_utage(image, Image.new("RGBA", (64, 64)), 64, 3)


def _pack_utage_group(name, cell_size, padding, entries):
    """Serialise a DicingTextures asset the way Unity lays its fields out."""
    def s(text):
        raw = text.encode("utf-8")
        return struct.pack("<i", len(raw)) + raw + b"\0" * (-len(raw) % 4)

    out = b"\0" * 12                       # m_GameObject
    out += b"\1" + b"\0" * 3               # m_Enabled + align
    out += b"\0" * 12                      # m_Script
    out += s(name)
    out += struct.pack("<ii", cell_size, padding)
    out += struct.pack("<i", 0)            # atlasTextures
    out += struct.pack("<i", len(entries))
    for entry_name, atlas, w, h, cells in entries:
        out += s(entry_name) + s(atlas) + struct.pack("<ii", w, h)
        out += struct.pack("<i", len(cells)) + b"".join(struct.pack("<i", c) for c in cells)
        out += struct.pack("<i", -1)       # transparentIndex
    return out


def test_parses_a_dicing_textures_asset():
    cells = list(range(math.ceil(300 / 58) * math.ceil(200 / 58)))
    raw = _pack_utage_group("Group", 64, 3, [("pic", "sheet", 300, 200, cells)])
    group = dicing.parse_utage_group(raw)

    assert group.name == "Group"
    assert (group.cell_size, group.padding, group.step) == (64, 3, 58)
    assert [i.name for i in group.images] == ["pic"]
    assert group.images[0].atlas == "sheet"
    assert group.images[0].cells == cells
    assert dicing.looks_like_utage_group(group) is True


def test_parsing_stops_when_the_layout_is_not_understood():
    cells = list(range(30))
    raw = _pack_utage_group("Group", 64, 3, [("pic", "sheet", 300, 200, cells)])
    with pytest.raises(dicing.DicingError, match="not understood"):
        dicing.parse_utage_group(raw + b"trailing")


def test_a_group_whose_cells_do_not_fit_its_grid_is_not_believed():
    """The filter that keeps unrelated MonoBehaviours from being mistaken for one."""
    raw = _pack_utage_group("Group", 64, 3, [("pic", "sheet", 300, 200, [0, 1, 2])])
    assert dicing.looks_like_utage_group(dicing.parse_utage_group(raw)) is False


def test_an_absurd_cell_size_is_not_believed():
    cells = list(range(math.ceil(300 / 94) * math.ceil(200 / 94)))
    raw = _pack_utage_group("Group", 100, 3, [("pic", "sheet", 300, 200, cells)])
    assert dicing.looks_like_utage_group(dicing.parse_utage_group(raw)) is False


# ── Naninovel SpriteDicing ───────────────────────────────────────────────

def _write_sprite_dicing(tmp_path, name, picture, unit=64, atlas_cols=4, seed=2):
    """Write a Sprite .json whose mesh points at a jumbled sheet, plus the sheet."""
    w, h = picture.size
    cols, rows = math.ceil(w / unit), math.ceil(h / unit)
    src = np.asarray(picture)[::-1]
    order = list(range(cols * rows))
    np.random.default_rng(seed).shuffle(order)

    atlas_rows = math.ceil(len(order) / atlas_cols)
    aw, ah = atlas_cols * unit, atlas_rows * unit
    atlas = np.zeros((ah, aw, 4), np.uint8)

    positions, uvs, indices = [], [], []
    for slot, grid_pos in enumerate(order):
        i, j = divmod(grid_pos, cols)
        y0, y1 = i * unit, min(i * unit + unit, h)
        x0, x1 = j * unit, min(j * unit + unit, w)
        ax, ay = (slot % atlas_cols) * unit, (slot // atlas_cols) * unit
        atlas[ay:ay + (y1 - y0), ax:ax + (x1 - x0)] = src[y0:y1, x0:x1]

        base = len(positions)
        for px, py, u, v in (
                (x0, y0, ax, ay), (x0, y1, ax, ay + (y1 - y0)),
                (x1, y1, ax + (x1 - x0), ay + (y1 - y0)), (x1, y0, ax + (x1 - x0), ay)):
            positions.append(((px - w / 2) / 100.0, (py - h / 2) / 100.0, 0.0))
            uvs.append((u / aw, v / ah))
        indices += [base, base + 1, base + 2, base + 2, base + 3, base]

    n = len(positions)
    pos_bytes = np.asarray(positions, np.float32).tobytes()
    pos_bytes += b"\0" * (-len(pos_bytes) % 16)         # streams are 16-aligned
    data = pos_bytes + np.asarray(uvs, np.float32).tobytes()
    channels = [{"m_Dimension": 0, "m_Format": 0, "m_Offset": 0, "m_Stream": 0}
                for _ in range(14)]
    channels[0] = {"m_Dimension": 3, "m_Format": 0, "m_Offset": 0, "m_Stream": 0}
    channels[4] = {"m_Dimension": 2, "m_Format": 0, "m_Offset": 0, "m_Stream": 1}

    (tmp_path / f"{name}.json").write_text(json.dumps({
        "m_Name": name,
        "m_Rect": {"m_Width": w, "m_Height": h, "m_X": 0, "m_Y": 0},
        "m_PixelsToUnits": 100,
        "m_RD": {
            "m_Texture": {"m_PathID": 4242},
            "m_IndexBuffer": base64.b64encode(
                np.asarray(indices, np.uint16).tobytes()).decode(),
            "m_VertexData": {"m_VertexCount": n,
                             "m_Channels": channels,
                             "m_Data": base64.b64encode(data).decode()},
        },
    }), encoding="utf-8")
    Image.fromarray(atlas[::-1], "RGBA").save(tmp_path / "sheet.png")
    return tmp_path / f"{name}.json", tmp_path / "sheet.png"


def test_sprite_dicing_rebuild_restores_the_original(tmp_path):
    picture = _picture(256, 192, seed=5)
    json_path, atlas_path = _write_sprite_dicing(tmp_path, "toy", picture)

    image = dicing.read_sprite_dicing(json_path)
    assert image is not None
    assert (image.width, image.height) == (256, 192)
    assert image.texture_id == 4242

    with Image.open(atlas_path) as atlas:
        rebuilt = dicing.rebuild_sprite_dicing(image, atlas)
    assert np.array_equal(np.asarray(rebuilt), np.asarray(picture))


def test_a_plain_single_quad_sprite_is_not_treated_as_diced(tmp_path):
    (tmp_path / "plain.json").write_text(json.dumps({
        "m_Name": "plain",
        "m_Rect": {"m_Width": 64, "m_Height": 64, "m_X": 0, "m_Y": 0},
        "m_RD": {"m_VertexData": {"m_VertexCount": 4, "m_Channels": [], "m_Data": ""},
                 "m_IndexBuffer": ""},
    }), encoding="utf-8")
    assert dicing.read_sprite_dicing(tmp_path / "plain.json") is None


def test_scan_skips_the_sheet_and_finds_it_as_the_atlas(tmp_path):
    picture = _picture(256, 192, seed=6)
    _write_sprite_dicing(tmp_path, "toy", picture)
    images, candidates = dicing.scan_sprite_dicing_folder(tmp_path)

    assert [i.name for i in images] == ["toy"]
    assert [p.name for p in candidates] == ["sheet.png"]


def test_choose_atlases_picks_the_sheet_that_leaves_no_seams(tmp_path):
    picture = _picture(256, 192, seed=7)
    _write_sprite_dicing(tmp_path, "toy", picture)
    # A decoy of the same size, but holding a different picture.
    decoy = _picture(256, 256, seed=99)
    decoy.save(tmp_path / "decoy.png")

    images, candidates = dicing.scan_sprite_dicing_folder(tmp_path)
    assert len(candidates) == 2
    chosen = dicing.choose_atlases(images, candidates)
    assert chosen[images[0].texture_id].name == "sheet.png"


# ── the seam check ───────────────────────────────────────────────────────

def test_a_correct_rebuild_passes_verification(tmp_path):
    picture = _picture(256, 192, seed=8)
    json_path, atlas_path = _write_sprite_dicing(tmp_path, "toy", picture)
    image = dicing.read_sprite_dicing(json_path)
    with Image.open(atlas_path) as atlas:
        rebuilt = dicing.rebuild_sprite_dicing(image, atlas)

    ok, excess = dicing.verify_rebuild(rebuilt, 64)
    assert ok is True
    assert excess < dicing.SEAM_TOLERANCE


def test_a_scrambled_rebuild_fails_verification():
    """Cells put back in the wrong order leave hard edges on the grid."""
    picture = _picture(256, 192, seed=9)
    cells = list(range(4 * 3))
    atlas, correct = _dice_utage(picture, 64, 0, atlas_cols=4, shuffle_seed=11)
    wrong = dicing.DicedImage("wrong", 256, 192, "sheet", cells=cells)
    scrambled = dicing.rebuild_utage(wrong, atlas, 64, 0)

    ok, excess = dicing.verify_rebuild(scrambled, 64)
    assert ok is False
    assert excess > dicing.SEAM_TOLERANCE


def test_verification_passes_when_there_is_nothing_to_measure():
    blank = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    ok, excess = dicing.verify_rebuild(blank, 64)
    assert ok is True and excess == 0.0
