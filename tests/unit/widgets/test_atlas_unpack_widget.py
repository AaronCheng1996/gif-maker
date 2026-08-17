"""Tests for the Atlas Unpack tab, driven against the widget directly."""
import base64
import json
import math

import numpy as np
import pytest
from PIL import Image

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core import dicing
from src.widgets.atlas_unpack_widget import AtlasUnpackWidget, Job


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


@pytest.fixture()
def widget(qapp):
    w = AtlasUnpackWidget()
    yield w
    # Qt aborts the process if a QThread outlives its widget.
    w.stop_workers()


def _picture(width, height, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width]
    r = (x * 255 // max(width - 1, 1)).astype(np.uint8)
    g = (y * 255 // max(height - 1, 1)).astype(np.uint8)
    b = ((x // 7 + y // 5) * 37 % 256).astype(np.uint8)
    a = np.full((height, width), 255, np.uint8)
    return Image.fromarray(
        np.dstack([r, g + rng.integers(0, 12, (height, width), dtype=np.uint8), b, a]), "RGBA")


def _write_diced(folder, name, picture, unit=64, atlas_cols=4, seed=2, sheet="sheet"):
    """A Sprite .json whose mesh points into a jumbled sheet, plus that sheet."""
    folder.mkdir(parents=True, exist_ok=True)
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
        for px, py, u, v in ((x0, y0, ax, ay), (x0, y1, ax, ay + (y1 - y0)),
                             (x1, y1, ax + (x1 - x0), ay + (y1 - y0)),
                             (x1, y0, ax + (x1 - x0), ay)):
            positions.append(((px - w / 2) / 100.0, (py - h / 2) / 100.0, 0.0))
            uvs.append((u / aw, v / ah))
        indices += [base, base + 1, base + 2, base + 2, base + 3, base]

    n = len(positions)
    pos_bytes = np.asarray(positions, np.float32).tobytes()
    pos_bytes += b"\0" * (-len(pos_bytes) % 16)
    channels = [{"m_Dimension": 0, "m_Format": 0, "m_Offset": 0, "m_Stream": 0}
                for _ in range(14)]
    channels[0] = {"m_Dimension": 3, "m_Format": 0, "m_Offset": 0, "m_Stream": 0}
    channels[4] = {"m_Dimension": 2, "m_Format": 0, "m_Offset": 0, "m_Stream": 1}
    (folder / f"{name}.json").write_text(json.dumps({
        "m_Name": name,
        "m_Rect": {"m_Width": w, "m_Height": h, "m_X": 0, "m_Y": 0},
        "m_PixelsToUnits": 100,
        "m_RD": {
            "m_Texture": {"m_PathID": 4242},
            "m_IndexBuffer": base64.b64encode(np.asarray(indices, np.uint16).tobytes()).decode(),
            "m_VertexData": {
                "m_VertexCount": n, "m_Channels": channels,
                "m_Data": base64.b64encode(
                    pos_bytes + np.asarray(uvs, np.float32).tobytes()).decode()},
        },
    }), encoding="utf-8")
    Image.fromarray(atlas[::-1], "RGBA").save(folder / f"{sheet}.png")


@pytest.fixture()
def ripped(tmp_path):
    """Folders of diced sprites, the way a ripper lays them out.

    One sprite per folder: each writes its own sheet, so sharing a folder would
    have them overwrite each other's."""
    _write_diced(tmp_path / "out" / "CG_01", "cg_a", _picture(256, 192, 1))
    _write_diced(tmp_path / "out" / "CG_02", "cg_b", _picture(256, 192, 2))
    _write_diced(tmp_path / "out" / "CG_03", "cg_c", _picture(128, 128, 3))
    return tmp_path / "out"


def _scan(widget, path, qapp):
    widget.load(path)
    assert widget._scan_worker.wait(60000)
    qapp.processEvents()


def test_starts_empty(widget):
    assert widget.jobs == []
    assert widget.image_list.count() == 0
    assert widget.extract_btn.isEnabled() is False


def test_scanning_a_ripped_folder_lists_every_diced_sprite(widget, ripped, qapp):
    _scan(widget, ripped, qapp)
    assert len(widget.jobs) == 3
    assert widget.image_list.count() == 3
    assert sorted(j.image.name for j in widget.jobs) == ["cg_a", "cg_b", "cg_c"]
    assert "3 images" in widget.source_label.text()


def test_a_folder_with_nothing_diced_reports_so(widget, tmp_path, qapp):
    (tmp_path / "empty").mkdir()
    _scan(widget, tmp_path / "empty", qapp)
    assert widget.jobs == []
    assert widget.extract_btn.isEnabled() is False


def test_preview_rebuilds_the_selected_image(widget, ripped, qapp):
    _scan(widget, ripped, qapp)
    widget.image_list.setCurrentRow(0)
    qapp.processEvents()

    pixmap = widget.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert "clean" in widget.preview_status.text()


def test_filter_hides_non_matching_rows(widget, ripped, qapp):
    _scan(widget, ripped, qapp)
    widget.filter_box.setText("cg_c")
    qapp.processEvents()
    visible = [widget.image_list.item(i).text() for i in range(widget.image_list.count())
               if not widget.image_list.item(i).isHidden()]
    assert len(visible) == 1 and "cg_c" in visible[0]


def test_extract_writes_one_png_per_image_grouped_by_folder(widget, ripped, qapp,
                                                            tmp_path, monkeypatch):
    _scan(widget, ripped, qapp)
    out = tmp_path / "written"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    widget.select_all_images()
    qapp.processEvents()
    widget.extract()
    assert widget._rebuild_worker.wait(120000)
    qapp.processEvents()

    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.png"))
    assert written == ["CG_01/cg_a.png", "CG_02/cg_b.png", "CG_03/cg_c.png"]


def test_extracted_image_matches_the_original(widget, ripped, qapp, tmp_path, monkeypatch):
    original = _picture(256, 192, 1)
    out = tmp_path / "written"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    _scan(widget, ripped, qapp)
    widget.image_list.setCurrentRow(
        next(i for i in range(widget.image_list.count())
             if "cg_a" in widget.image_list.item(i).text()))
    qapp.processEvents()
    widget.extract()
    assert widget._rebuild_worker.wait(120000)
    qapp.processEvents()

    with Image.open(out / "CG_01" / "cg_a.png") as rebuilt:
        assert np.array_equal(np.asarray(rebuilt), np.asarray(original))


def test_a_rebuild_that_cannot_be_trusted_is_not_written(widget, ripped, qapp,
                                                         tmp_path, monkeypatch):
    """The seam check is what stops a scrambled picture reaching the disk."""
    _scan(widget, ripped, qapp)
    monkeypatch.setattr(dicing, "verify_rebuild", lambda img, step: (False, 42.0))
    out = tmp_path / "written"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    widget.select_all_images()
    qapp.processEvents()
    widget.extract()
    assert widget._rebuild_worker.wait(120000)
    qapp.processEvents()

    assert list(out.rglob("*.png")) == []
    assert "3 skipped" in widget.preview_status.text()


def test_output_defaults_to_an_output_folder_beside_the_rip(widget, ripped, qapp):
    _scan(widget, ripped, qapp)
    assert widget.default_output_dir() == ripped / "output"


def test_output_for_a_unity_file_lands_next_to_the_rip(widget, tmp_path):
    """A game folder holds both `out/` and the data folder; both go to the same place."""
    (tmp_path / "out").mkdir()
    data = tmp_path / "Game_Data"
    data.mkdir()
    source = data / "resources.assets"
    source.write_bytes(b"")
    widget.source = source
    assert widget.default_output_dir() == tmp_path / "out" / "output"


def test_extract_button_counts_the_selection(widget, ripped, qapp):
    _scan(widget, ripped, qapp)
    widget.select_all_images()
    qapp.processEvents()
    assert "3" in widget.extract_btn.text()


def test_stop_workers_is_idempotent(widget):
    widget.stop_workers()
    widget.stop_workers()
