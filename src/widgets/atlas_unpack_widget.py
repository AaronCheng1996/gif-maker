"""Atlas Unpack — rebuild pictures a game stored as diced texture atlases.

Some engines cut every picture into a grid of cells, drop the cells that repeat
and pack the rest into one sheet, so forty expression variants of a character
cost barely more than one. The sheet looks like noise and the pictures only come
back with the table that says which cell goes where.

Two sources are handled, and which one applies is worked out from what is
dropped on the tab:

* a **folder** of asset-ripper output — Naninovel SpriteDicing keeps a mesh per
  sprite in the exported `.json`, so nothing else is needed;
* a Unity **`.assets` file or bundle** — Utage keeps a cell index list inside a
  ScriptableObject that rippers usually skip, so this reads the game's own data
  and needs UnityPy.

Every rebuild is checked before it is written: pairing a sprite with the wrong
sheet leaves hard edges on the cell grid, and that is measurable without having
the original to compare against.
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
                             QProgressBar, QSplitter, QSizePolicy, QAbstractItemView,
                             QLineEdit, QGroupBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from PIL import Image

from ..i18n import tr
from ..core import dicing
from .theme import AppTheme as _T
from . import ui

PREVIEW_MAX = 640
UNITY_SUFFIXES = (".assets", ".bundle", ".unity3d")


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimg)
    del data
    return pixmap


class Job:
    """One rebuildable picture together with everything needed to rebuild it."""

    __slots__ = ("group", "image", "atlas_path", "atlas_name", "cell_size", "padding", "kind")

    def __init__(self, group: str, image: dicing.DicedImage, kind: str,
                 atlas_path: Optional[Path] = None, atlas_name: str = "",
                 cell_size: int = 64, padding: int = 0):
        self.group = group
        self.image = image
        self.kind = kind                 # "utage" | "spritedicing"
        self.atlas_path = atlas_path     # spritedicing: the sheet on disk
        self.atlas_name = atlas_name     # utage: the sheet's name inside the game
        self.cell_size = cell_size
        self.padding = padding

    @property
    def step(self) -> int:
        return self.cell_size - 2 * self.padding


class _ScanWorker(QThread):
    """Works out what a folder or Unity file contains, without rebuilding anything."""
    done = pyqtSignal(list, str)     # jobs, summary
    error = pyqtSignal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            if self.path.is_dir():
                jobs, note = self._scan_folder(self.path)
            else:
                jobs, note = self._scan_unity(self.path)
            self.done.emit(jobs, note)
        except dicing.DicingError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _scan_folder(self, root: Path):
        jobs: List[Job] = []
        folders = [root] + [p for p in sorted(root.rglob("*")) if p.is_dir()]
        without_atlas = 0
        for folder in folders:
            images, candidates = dicing.scan_sprite_dicing_folder(folder)
            if not images:
                continue
            if not candidates:
                without_atlas += len(images)
                continue
            chosen = dicing.choose_atlases(images, candidates)
            for image in images:
                path = chosen.get(image.texture_id)
                if path is None:
                    without_atlas += 1
                    continue
                jobs.append(Job(folder.name, image, "spritedicing", atlas_path=path))
        note = f"{len(jobs)} images in {len({j.group for j in jobs})} folders"
        if without_atlas:
            note += f"  ·  {without_atlas} skipped, their sheet is not in the export"
        return jobs, note

    def _scan_unity(self, path: Path):
        groups = dicing.read_utage_groups(path)
        jobs = [Job(g.name, image, "utage", atlas_name=image.atlas,
                    cell_size=g.cell_size, padding=g.padding)
                for g in groups for image in g.images]
        return jobs, f"{len(jobs)} images in {len(groups)} dicing groups"


class _RebuildWorker(QThread):
    """Rebuilds jobs and writes them out, checking each one before it lands."""
    progress = pyqtSignal(int, int, str)      # done, total, current name
    done = pyqtSignal(int, list)              # written, [(name, reason)]
    error = pyqtSignal(str)

    def __init__(self, jobs: List[Job], out_dir: Path, source: Path, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.out_dir = out_dir
        self.source = source
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            written, failures = 0, []
            textures: Dict[str, Optional[Image.Image]] = {}
            for i, job in enumerate(self.jobs):
                if self._cancelled:
                    break
                self.progress.emit(i, len(self.jobs), job.image.name)
                try:
                    rebuilt = self._rebuild(job, textures)
                except Exception as e:
                    failures.append((job.image.name, str(e)))
                    continue
                if rebuilt is None:
                    failures.append((job.image.name, "sheet unavailable"))
                    continue
                ok, excess = dicing.verify_rebuild(rebuilt, job.step)
                if not ok:
                    failures.append((job.image.name,
                                     f"cell seams stand out by {excess:+.1f}; wrong sheet?"))
                    continue
                folder = self.out_dir / job.group
                folder.mkdir(parents=True, exist_ok=True)
                rebuilt.save(folder / f"{job.image.name}.png")
                written += 1
            self.progress.emit(len(self.jobs), len(self.jobs), "")
            self.done.emit(written, failures)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _rebuild(self, job: Job, textures) -> Optional[Image.Image]:
        if job.kind == "spritedicing":
            key = str(job.atlas_path)
            if key not in textures:
                textures.clear()          # sheets are large; hold one at a time
                textures[key] = Image.open(job.atlas_path).convert("RGBA")
            return dicing.rebuild_sprite_dicing(job.image, textures[key])

        if "utage" not in textures:
            textures.clear()
            textures["utage"] = dicing.load_utage_textures(self.source)
        atlas = textures["utage"].get(job.atlas_name)
        if atlas is None:
            return None
        return dicing.rebuild_utage(job.image, atlas, job.cell_size, job.padding)


class AtlasUnpackWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source: Optional[Path] = None
        self.jobs: List[Job] = []
        self.last_dir = ""
        self._scan_worker: Optional[_ScanWorker] = None
        self._rebuild_worker: Optional[_RebuildWorker] = None
        self._current_pixmap: Optional[QPixmap] = None
        self._init_ui()
        self._update_enabled_state()

    # ── UI ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = ui.tab_layout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([420, 700])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        title = QLabel(tr("Diced Atlas"))
        title.setStyleSheet(ui.TITLE_QSS)
        v.addWidget(title)

        self.open_folder_btn = QPushButton(tr("📂 Open Ripped Folder…"))
        self.open_folder_btn.setToolTip(
            "A folder of asset-ripper output. Sprite .json files that carry a dicing "
            "mesh are rebuilt against the sheet sitting beside them.")
        self.open_folder_btn.clicked.connect(self.open_folder)
        v.addWidget(self.open_folder_btn)

        self.open_unity_btn = QPushButton(tr("📦 Open Unity .assets…"))
        self.open_unity_btn.setToolTip(
            "The game's own resources.assets or a bundle. Reads the cell index "
            "tables that rippers usually leave behind. Needs UnityPy.")
        self.open_unity_btn.clicked.connect(self.open_unity_file)
        v.addWidget(self.open_unity_btn)

        self.source_label = QLabel(tr("Nothing loaded"))
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.source_label)

        header = QHBoxLayout()
        images_label = QLabel(tr("Images"))
        images_label.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {_T.TEXT_DIM};")
        header.addWidget(images_label)
        header.addStretch()
        self.select_all_btn = QPushButton(tr("Select All"))
        self.select_all_btn.setFixedHeight(22)
        self.select_all_btn.clicked.connect(self.select_all_images)
        header.addWidget(self.select_all_btn)
        v.addLayout(header)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText(tr("Filter by name"))
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.textChanged.connect(self._apply_filter)
        v.addWidget(self.filter_box)

        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.image_list.currentRowChanged.connect(self._on_image_selected)
        self.image_list.itemSelectionChanged.connect(self._update_extract_button)
        v.addWidget(self.image_list, stretch=1)

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        self.preview_label = QLabel(tr("Open a ripped folder or a Unity .assets file"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumSize(320, 320)
        self.preview_label.setStyleSheet(
            f"background-color: {_T.CARD}; border: 1px solid {_T.BORDER}; border-radius: 4px;"
            f" color: {_T.TEXT_HINT};")
        v.addWidget(self.preview_label, stretch=1)

        self.preview_status = QLabel("")
        self.preview_status.setWordWrap(True)
        self.preview_status.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.preview_status)

        box = QGroupBox(tr("Extract"))
        g = QVBoxLayout()
        hint = QLabel(tr("Each picture is checked before it is written: if its cell "
                         "borders stand out, it is reported instead of saved."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_T.TEXT_HINT}; font-size: 10px;")
        g.addWidget(hint)

        self.extract_btn = QPushButton(tr("💾 Extract"))
        self.extract_btn.setStyleSheet(ui.GO_QSS)
        self.extract_btn.clicked.connect(self.extract)
        g.addWidget(self.extract_btn)

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        g.addWidget(self.cancel_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        g.addWidget(self.progress_bar)
        box.setLayout(g)
        v.addWidget(box)

        return panel

    # ── loading ──────────────────────────────────────────────────────────

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr("Open Ripped Folder"), self.last_dir)
        if path:
            self.load(Path(path))

    def open_unity_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open Unity .assets"), self.last_dir,
            "Unity data (*.assets *.bundle *.unity3d);;All files (*)")
        if path:
            self.load(Path(path))

    def load(self, path: Path):
        self.source = path
        self.last_dir = str(path if path.is_dir() else path.parent)
        self.jobs = []
        self.image_list.clear()
        self.source_label.setText(tr("Scanning…"))
        self.open_folder_btn.setEnabled(False)
        self.open_unity_btn.setEnabled(False)
        self._scan_worker = _ScanWorker(path, self)
        self._scan_worker.done.connect(self._on_scanned)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scanned(self, jobs: list, note: str):
        self.open_folder_btn.setEnabled(True)
        self.open_unity_btn.setEnabled(True)
        self.jobs = jobs
        self.image_list.blockSignals(True)
        self.image_list.clear()
        for job in jobs:
            item = QListWidgetItem(
                f"{job.group} / {job.image.name}\n"
                f"{job.image.width}×{job.image.height}  ·  {job.image.megapixels:.1f} MP")
            item.setData(Qt.ItemDataRole.UserRole, job)
            self.image_list.addItem(item)
        self.image_list.blockSignals(False)
        self.source_label.setText(f"{self.source}\n{note}" if self.source else note)
        self._update_enabled_state()
        self._update_extract_button()
        if jobs:
            self.image_list.setCurrentRow(0)
        else:
            self.preview_label.setText(tr("Nothing diced was found here"))

    def _on_scan_error(self, message: str):
        self.open_folder_btn.setEnabled(True)
        self.open_unity_btn.setEnabled(True)
        self.source_label.setText(tr("Nothing loaded"))
        self._update_enabled_state()
        QMessageBox.critical(self, "Error", f"Could not read this source:\n{message}")

    # ── list / preview ───────────────────────────────────────────────────

    def select_all_images(self):
        self.image_list.selectAll()

    def selected_jobs(self) -> List[Job]:
        items = self.image_list.selectedItems()
        if not items and self.image_list.currentItem():
            items = [self.image_list.currentItem()]
        return [i.data(Qt.ItemDataRole.UserRole) for i in items]

    def _apply_filter(self, text: str):
        needle = text.strip().lower()
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _on_image_selected(self, _row: int):
        job = self.image_list.currentItem()
        job = job.data(Qt.ItemDataRole.UserRole) if job else None
        if job is None or job.kind != "spritedicing":
            # Previewing a Utage image would mean decoding a sheet out of the
            # game file, which is far too slow to do on every click.
            self.preview_label.setText(tr("Preview available after extracting"))
            self._current_pixmap = None
            self.preview_status.setText(
                f"{job.image.width}×{job.image.height}" if job else "")
            return
        try:
            with Image.open(job.atlas_path) as atlas:
                rebuilt = dicing.rebuild_sprite_dicing(job.image, atlas)
        except Exception as e:
            self.preview_status.setText(f"Preview failed: {e}")
            return
        ok, excess = dicing.verify_rebuild(rebuilt, job.step)
        self._current_pixmap = _pil_to_pixmap(rebuilt)
        self._paint_preview()
        verdict = "clean" if ok else f"cell seams stand out by {excess:+.1f} — wrong sheet?"
        self.preview_status.setText(
            f"{rebuilt.width}×{rebuilt.height}  ·  {job.atlas_path.name}  ·  {verdict}")

    def _paint_preview(self):
        pixmap = self._current_pixmap
        if pixmap is None or pixmap.isNull():
            return
        avail = self.preview_label.size()
        if avail.width() > 1 and avail.height() > 1:
            pixmap = pixmap.scaled(avail, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_preview()

    # ── extract ──────────────────────────────────────────────────────────

    def _update_extract_button(self):
        count = len(self.selected_jobs())
        self.extract_btn.setText(
            tr("💾 Extract {n} images").replace("{n}", str(count)) if count > 1
            else tr("💾 Extract"))

    def default_output_dir(self) -> Optional[Path]:
        """Where rebuilt pictures should land: an `output` folder beside the rip.

        A ripped tree usually sits under `out/`, and the game's own data folder
        sits next to it, so both kinds of source are steered to the same place
        rather than one of them dropping files inside the game install."""
        if self.source is None:
            return None
        base = self.source if self.source.is_dir() else self.source.parent
        candidates = [base] + list(base.parents)
        for parent in candidates:
            if parent.name.lower() == "out":
                return parent / "output"
        for parent in candidates:
            sibling = parent / "out"
            if sibling.is_dir():
                return sibling / "output"
        return base / "output"

    def extract(self):
        jobs = self.selected_jobs()
        if not jobs:
            QMessageBox.warning(self, "Warning", "Select at least one image first!")
            return
        default = self.default_output_dir()
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Select Output Folder"), str(default) if default else "")
        if not chosen:
            return
        out_dir = Path(chosen)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(jobs))
        self.progress_bar.setValue(0)
        self.extract_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

        self._rebuild_worker = _RebuildWorker(jobs, out_dir, self.source, self)
        self._rebuild_worker.progress.connect(self._on_progress)
        self._rebuild_worker.done.connect(self._on_extract_done)
        self._rebuild_worker.error.connect(self._on_extract_error)
        self._rebuild_worker.start()

    def _on_progress(self, current: int, total: int, name: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if name:
            self.preview_status.setText(f"Rebuilding {name}  ({current + 1}/{total})")

    def _finish(self):
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.extract_btn.setEnabled(True)

    def _on_extract_done(self, written: int, failures: list):
        self._finish()
        message = f"Rebuilt {written} images."
        if failures:
            listed = "\n".join(f"· {n}: {why}" for n, why in failures[:10])
            more = f"\n…and {len(failures) - 10} more" if len(failures) > 10 else ""
            message += f"\n\n{len(failures)} could not be trusted:\n{listed}{more}"
        QMessageBox.information(self, "Atlas Unpack", message)
        self.preview_status.setText(f"Rebuilt {written} images, {len(failures)} skipped")

    def _on_extract_error(self, message: str):
        self._finish()
        QMessageBox.critical(self, "Error", f"Extraction failed:\n{message}")

    def _cancel(self):
        if self._rebuild_worker is not None:
            self._rebuild_worker.cancel()
        self.cancel_btn.setEnabled(False)

    # ── misc ─────────────────────────────────────────────────────────────

    def _update_enabled_state(self):
        has = bool(self.jobs)
        for w in (self.image_list, self.filter_box, self.select_all_btn, self.extract_btn):
            w.setEnabled(has)

    def stop_workers(self, timeout_ms: int = 30000):
        """Qt aborts the process if a QThread outlives its widget."""
        if self._rebuild_worker is not None:
            self._rebuild_worker.cancel()
        for worker in (self._scan_worker, self._rebuild_worker):
            if worker is not None and worker.isRunning():
                worker.wait(timeout_ms)

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
