"""
Batch processor - generate GIFs from multiple images using a composition template.

Workflow per image
──────────────────
1. Load image and split into tiles.
2. (Optional) filter tiles by selected positions.
3. Create a temporary MaterialManager populated with the tile images.
4. Restore a GroupManager from the template (material indices = tile positions).
5. Build GIF with GifBuilder.build_gif_from_group().
6. Save to output path.
"""
import copy
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path

from PIL import Image

from .image_loader import ImageLoader, MaterialManager
from .gif_builder import GifBuilder
from .template_manager import TemplateManager


class BatchProcessingError(Exception):
    pass


class BatchProcessor:

    def __init__(self):
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        self.progress_callback = callback

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

            # ── 4. Validate and restore GroupManager ──────────────────────────
            TemplateManager.validate_template(template)

            required = TemplateManager.estimate_required_tiles(template)
            if len(mm) < required:
                raise BatchProcessingError(
                    f"Template requires {required} tiles; only {len(mm)} generated"
                )

            group_manager, settings = TemplateManager.import_composition_template(template)

            # ── 5. Build GIF ──────────────────────────────────────────────────
            gif_builder = GifBuilder()

            w = output_width if output_width is not None else settings.get("output_width", 256)
            h = output_height if output_height is not None else settings.get("output_height", 256)
            gif_builder.set_output_size(w, h)
            gif_builder.set_loop(settings.get("loop_count", 0))
            gif_builder.set_color_count(color_count)

            if settings.get("transparent_bg", False):
                gif_builder.set_background_color(0, 0, 0, 0)
            else:
                gif_builder.set_background_color(255, 255, 255, 255)

            if output_path is None:
                output_path = str(Path(image_path).with_suffix(".gif"))

            root_gid = group_manager.get_root_group_id()
            if root_gid is None:
                raise BatchProcessingError("Template has no root group")

            gif_builder.build_gif_from_group(root_gid, group_manager, mm, output_path)
            return output_path

        except BatchProcessingError:
            raise
        except Exception as e:
            import traceback
            msg = f"Failed to process {Path(image_path).name}: {e}\n{traceback.format_exc()}"
            print(msg)
            raise BatchProcessingError(msg)

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
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Process multiple images into GIFs with the same template.

        Returns (successful_paths, [(img_path, error_msg), ...]).
        """
        successful: List[str] = []
        failed: List[Tuple[str, str]] = []
        total = len(image_paths)

        for idx, image_path in enumerate(image_paths, 1):
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
                    output_width, output_height,
                )
                successful.append(result)
                self._report_progress(idx, total, f"Done {Path(image_path).name}")

            except Exception as e:
                failed.append((image_path, str(e)))
                self._report_progress(idx, total, f"Failed {Path(image_path).name}: {e}")

        return successful, failed

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
