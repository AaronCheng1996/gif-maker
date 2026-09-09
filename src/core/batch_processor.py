"""
Batch processor - generate GIFs from many sources using one composition template.

There are two kinds of source, and they differ only in where the materials come
from:

Sprite sheet (process_single_image)
    1. Load image and split into tiles.
    2. (Optional) filter tiles by selected positions.
    3. Materials are the tiles, named by position.

Frame folder (process_frame_set)
    1. Group the folder into one unit per output — see core/frame_set.py.
    2. Materials are the files of one unit, named by file stem, so a template
       whose groups are bound to a glob (CompositionGroup.source_pattern) picks
       its own clips out of them.

From there both run the same way: restore a GroupManager from the template,
build with GifBuilder.build_gif_from_group(), save.
"""
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path

from PIL import Image

from .composition_group import (
    is_group_slot, is_layer_block_entry, is_sub_group_entry,
    resolve_source_indices,
)
from .image_loader import ImageLoader, MaterialManager
from .frame_set import FrameSet, FrameScan, scan_frame_folder
from .gif_builder import GifBuilder
from .template_manager import TemplateManager


class BatchProcessingError(Exception):
    pass


def _reachable_groups(group_manager, root_gid: int):
    """The groups a build would actually visit, root first.

    Mirrors GifBuilder._expand_composition_group, including the part that makes
    a bound group a leaf: while source_pattern is set its entries are kept but
    not exported, so nothing under it is reached and nothing under it should be
    reported on.
    """
    seen = set()
    stack = [root_gid]
    while stack:
        gid = stack.pop()
        if gid in seen:
            continue
        seen.add(gid)
        group = group_manager.get_group(gid)
        if group is None:
            continue
        yield group
        if group.source_pattern:
            continue
        for entry in group.entries:
            if is_sub_group_entry(entry):
                stack.append(entry.group_id)
            elif is_layer_block_entry(entry):
                for timeline in entry.timelines:
                    for slot in timeline:
                        if is_group_slot(slot):
                            stack.append(slot.group_id)


def empty_bound_groups(group_manager, root_gid: int,
                       names: List[str]) -> List[str]:
    """Which of the reachable bound groups this material set would leave empty.

    A group bound to a glob that matches nothing contributes no frames, and the
    GIF is written anyway - one animation short, with no error to notice. Over a
    folder of a couple of hundred units that is the failure that costs the most
    to find, because the run says it succeeded and the difference is only
    visible by opening the file. Checked on names alone, so it can be run before
    a batch as easily as during one.
    """
    return [
        f"group '{g.name}' is bound to '{g.source_pattern}' and no material matches"
        for g in _reachable_groups(group_manager, root_gid)
        if g.source_pattern and not resolve_source_indices(g.source_pattern, names)
    ]


def check_material_coverage(template: Dict[str, Any],
                            names: List[str]) -> List[str]:
    """empty_bound_groups for a template that has not been imported yet.

    The pre-flight half: what a unit's file names would leave empty, answerable
    from a scan without loading a single image."""
    try:
        group_manager, _ = TemplateManager.import_composition_template(template)
    except Exception:
        return []                       # a template this broken fails the build
    root_gid = group_manager.get_root_group_id()
    if root_gid is None:
        return []
    return empty_bound_groups(group_manager, root_gid, names)


class BatchProcessor:

    def __init__(self):
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None
        self._cancelled = False
        # What the last _build_from_materials found wrong with its material set.
        # Kept on the processor rather than returned so both sources get the
        # check from the one place that has the real materials.
        self.last_warnings: List[str] = []

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        self.progress_callback = callback

    def cancel(self) -> None:
        """Ask a running batch to stop after the item it is on.

        A folder can hold dozens of units, so a run is long enough that quitting
        the app during one is ordinary rather than exceptional — and the thread
        has to end before its widget does. Checked between items, never inside
        one, so no half-written GIF is left behind."""
        self._cancelled = True

    def _report_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)

    # ─────────────────────────────────────────────────────────────────────────

    def process_single_image(
        self,
        image_path: str,
        template: Dict[str, Any],
        split_mode: str,
        split_rows: int,
        split_cols: int,
        tile_width: int,
        tile_height: int,
        color_count: int = 256,
        output_path: Optional[str] = None,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None,
        auto_size: bool = False,
    ) -> str:
        """
        Process one image into a GIF using a composition template.

        Returns the path of the created GIF.
        Raises BatchProcessingError on failure.
        """
        try:
            # ── 1. Load + split ───────────────────────────────────────────────
            image = ImageLoader.load_image(image_path)

            if split_mode == "grid":
                tiles = ImageLoader.split_into_tiles(image, split_rows, split_cols)
            else:
                tiles = ImageLoader.split_by_tile_size(image, tile_width, tile_height)

            # ── 2. Filter tiles ───────────────────────────────────────────────
            if selected_positions:
                cols = split_cols if split_mode == "grid" else (image.size[0] // tile_width)
                filtered = []
                for row, col in selected_positions:
                    idx = row * cols + col
                    if idx < len(tiles):
                        filtered.append(tiles[idx])
                tiles = filtered

            if not tiles:
                raise BatchProcessingError("No tiles generated after filtering")

            # ── 3. Temporary MaterialManager ──────────────────────────────────
            mm = MaterialManager()
            stem = Path(image_path).stem
            for i, tile in enumerate(tiles):
                mm.add_material(tile, f"{stem}_tile_{i}")

            # ── 4-6. Template, build, save ────────────────────────────────────
            if output_path is None:
                output_path = str(Path(image_path).with_suffix(".gif"))
            return self._build_from_materials(
                mm, template, output_path,
                color_count=color_count,
                output_width=output_width, output_height=output_height,
                auto_size=auto_size, units="tiles",
            )

        except BatchProcessingError:
            raise
        except Exception as e:
            import traceback
            msg = f"Failed to process {Path(image_path).name}: {e}\n{traceback.format_exc()}"
            print(msg)
            raise BatchProcessingError(msg)

    # ─────────────────────────────────────────────────────────────────────────

    def _build_from_materials(
        self,
        mm: MaterialManager,
        template: Dict[str, Any],
        output_path: str,
        color_count: int = 256,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None,
        auto_size: bool = False,
        units: str = "materials",
    ) -> str:
        """Run a template over a material set and write the GIF.

        The half both sources share: everything after 'where did the materials
        come from' is the same work, and keeping one copy of it is what stops
        the two paths drifting on palette, background or output size."""
        TemplateManager.validate_template(template)

        required = TemplateManager.estimate_required_tiles(template)
        if len(mm) < required:
            raise BatchProcessingError(
                f"Template requires {required} {units}; only {len(mm)} available"
            )

        group_manager, settings = TemplateManager.import_composition_template(template)

        root_gid = group_manager.get_root_group_id()
        if root_gid is None:
            raise BatchProcessingError("Template has no root group")

        self.last_warnings = empty_bound_groups(
            group_manager, root_gid,
            [name for _, name in mm.get_all_materials()])

        gif_builder = GifBuilder()

        # One size across a batch either crops the tall sources or pads the
        # small ones, and with a frame folder the sources are whole characters
        # that genuinely differ. Auto measures each one on its own materials.
        w = h = 0
        if auto_size:
            w, h = gif_builder.measure_group_output_size(root_gid, group_manager, mm)
        if w <= 0 or h <= 0:
            w = output_width if output_width is not None else settings.get("output_width", 256)
            h = output_height if output_height is not None else settings.get("output_height", 256)
        gif_builder.set_output_size(w, h)
        gif_builder.set_loop(settings.get("loop_count", 0))
        gif_builder.set_color_count(color_count)

        if settings.get("transparent_bg", False):
            gif_builder.set_background_color(0, 0, 0, 0)
        else:
            gif_builder.set_background_color(255, 255, 255, 255)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        gif_builder.build_gif_from_group(root_gid, group_manager, mm, output_path)
        return output_path

    # ─────────────────────────────────────────────────────────────────────────

    def process_frame_set(
        self,
        frame_set: FrameSet,
        template: Dict[str, Any],
        color_count: int = 256,
        output_path: Optional[str] = None,
        output_directory: Optional[str] = None,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None,
        auto_size: bool = False,
    ) -> str:
        """Build one GIF from one unit's frames.

        Materials keep their file stems, which is what a template's group globs
        match on — bind a group to *_org* and it picks that clip out of whatever
        this unit happens to hold, however many frames that is.
        """
        if not frame_set.paths:
            raise BatchProcessingError(f"Unit '{frame_set.unit}' has no frames")
        try:
            mm = MaterialManager()
            for path in frame_set.paths:
                mm.add_material(ImageLoader.load_image(str(path)), Path(path).stem)

            if output_path is None:
                folder = Path(output_directory) if output_directory \
                    else Path(frame_set.paths[0]).parent
                output_path = str(folder / f"{frame_set.unit}.gif")

            return self._build_from_materials(
                mm, template, output_path,
                color_count=color_count,
                output_width=output_width, output_height=output_height,
                auto_size=auto_size, units="materials",
            )

        except BatchProcessingError:
            raise
        except Exception as e:
            import traceback
            msg = f"Failed to process unit {frame_set.unit}: {e}\n{traceback.format_exc()}"
            print(msg)
            raise BatchProcessingError(msg)

    def process_frame_folder(
        self,
        folder: str,
        pattern: Optional[str],
        template: Dict[str, Any],
        color_count: int = 256,
        output_directory: Optional[str] = None,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None,
        auto_size: bool = False,
        recursive: bool = False,
    ) -> Tuple[List[str], List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Build one GIF per unit found in `folder`.

        Returns (successful_paths, [(unit, error)], [(unit, warning)]).

        A warning is not a third kind of failure: the GIF was written and its
        path is in successful_paths. It says the file is worth opening - this
        unit did not fill one of the template's groups, so the output is an
        animation short rather than wrong, which nothing else would report. One
        unit naming its clips differently from the rest is the usual cause, and
        over a hundred units the only way to find it is a list.
        """
        scan: FrameScan = scan_frame_folder(folder, pattern, recursive=recursive)
        successful: List[str] = []
        failed: List[Tuple[str, str]] = []
        warnings: List[Tuple[str, str]] = []
        total = len(scan.units)

        for idx, unit in enumerate(scan.units, 1):
            if self._cancelled:
                self._report_progress(idx - 1, total, "Cancelled")
                break
            try:
                self._report_progress(idx, total, f"Processing {unit.unit}")
                successful.append(self.process_frame_set(
                    unit, template,
                    color_count=color_count,
                    output_directory=output_directory,
                    output_width=output_width, output_height=output_height,
                    auto_size=auto_size,
                ))
                warnings.extend((unit.unit, w) for w in self.last_warnings)
                self._report_progress(idx, total, f"Done {unit.unit}")
            except Exception as e:
                failed.append((unit.unit, str(e)))
                self._report_progress(idx, total, f"Failed {unit.unit}: {e}")

        return successful, failed, warnings

    # ─────────────────────────────────────────────────────────────────────────

    def process_batch(
        self,
        image_paths: List[str],
        template: Dict[str, Any],
        split_mode: str,
        split_rows: int,
        split_cols: int,
        tile_width: int,
        tile_height: int,
        color_count: int = 256,
        output_directory: Optional[str] = None,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None,
        auto_size: bool = False,
    ) -> Tuple[List[str], List[Tuple[str, str]], List[Tuple[str, str]]]:
        """
        Process multiple images into GIFs with the same template.

        Returns (successful_paths, [(img_path, error)], [(img_path, warning)]).
        A warning means the GIF was written but a group of the template found no
        tile to fill it - see process_frame_folder, which reports the same way.
        """
        successful: List[str] = []
        failed: List[Tuple[str, str]] = []
        warnings: List[Tuple[str, str]] = []
        total = len(image_paths)

        for idx, image_path in enumerate(image_paths, 1):
            if self._cancelled:
                self._report_progress(idx - 1, total, "Cancelled")
                break
            try:
                self._report_progress(idx, total, f"Processing {Path(image_path).name}")

                out = (
                    str(Path(output_directory) / f"{Path(image_path).stem}.gif")
                    if output_directory
                    else None
                )

                result = self.process_single_image(
                    image_path, template,
                    split_mode, split_rows, split_cols,
                    tile_width, tile_height,
                    color_count, out, selected_positions,
                    output_width, output_height, auto_size,
                )
                successful.append(result)
                warnings.extend((image_path, w) for w in self.last_warnings)
                self._report_progress(idx, total, f"Done {Path(image_path).name}")

            except Exception as e:
                failed.append((image_path, str(e)))
                self._report_progress(idx, total, f"Failed {Path(image_path).name}: {e}")

        return successful, failed, warnings

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def validate_template(template: Dict[str, Any]) -> bool:
        """Raise ValueError if invalid, return True if OK."""
        return TemplateManager.validate_template(template)

    @staticmethod
    def estimate_required_tiles(template: Dict[str, Any]) -> int:
        return TemplateManager.estimate_required_tiles(template)

    @staticmethod
    def validate_template_for_batch(
        template: Dict[str, Any],
        split_mode: str,
        split_rows: int,
        split_cols: int,
        tile_width: int,
        tile_height: int,
        image_width: int,
        image_height: int,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
    ) -> Tuple[bool, str]:
        """
        Check template compatibility with batch split settings.

        Returns (is_valid, message).
        """
        try:
            BatchProcessor.validate_template(template)
        except ValueError as e:
            return False, f"Invalid template: {e}"

        if split_mode == "grid":
            total_tiles = split_rows * split_cols
        else:
            total_tiles = (image_width // tile_width) * (image_height // tile_height)

        available = len(selected_positions) if selected_positions else total_tiles
        if available == 0:
            return False, "No tiles will be generated with current settings"

        required = BatchProcessor.estimate_required_tiles(template)
        if required > available:
            return False, (
                f"Template needs {required} tiles, but only {available} will be generated. "
                "Adjust split settings or select more positions."
            )

        return True, (
            f"✓ Compatible: needs {required} tiles, {available} will be generated"
        )
