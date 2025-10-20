"""
Batch Processor - Automate tile splitting and GIF generation for multiple images

This module provides batch processing functionality:
1. Load multiple images
2. Split each image into tiles (e.g., 4x4 grid)
3. Apply a template to generate layered frames
4. Export as GIF to the same directory as the source image
"""

from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Callable
from PIL import Image

from .image_loader import ImageLoader, MaterialManager
from .template_manager import TemplateManager
from .layered_sequence_editor import LayeredSequenceEditor
from .gif_builder import GifBuilder


class BatchProcessingError(Exception):
    """Exception raised during batch processing"""
    pass


class BatchProcessor:
    """
    Handles batch processing of images with tile splitting and template application
    """
    
    def __init__(self):
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set callback for progress updates
        
        Args:
            callback: Function(current: int, total: int, message: str)
        """
        self.progress_callback = callback
    
    def _report_progress(self, current: int, total: int, message: str):
        """Report progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def process_single_image(
        self,
        image_path: str,
        template: Dict[str, Any],
        split_mode: str,
        split_rows: int = 4,
        split_cols: int = 4,
        tile_width: int = 32,
        tile_height: int = 32,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
        output_path: Optional[str] = None,
        color_count: int = 256
    ) -> str:
        """
        Process a single image: split tiles → apply template → export GIF
        
        Args:
            image_path: Path to source image
            template: Template dictionary (from TemplateManager)
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid mode
            split_cols: Number of columns for grid mode
            tile_width: Tile width for size mode
            tile_height: Tile height for size mode
            selected_positions: List of (row, col) positions to keep, None = all
            output_path: Output GIF path, None = auto (replace extension)
            color_count: Number of colors in the palette (256, 128, 64, 32, 16)
        
        Returns:
            Output GIF file path
        
        Raises:
            BatchProcessingError: If processing fails
        """
        try:
            # Load source image
            img = Image.open(image_path)
            
            # Split into tiles
            if split_mode == "grid":
                tiles = ImageLoader.split_into_tiles(img, split_rows, split_cols)
                cols = split_cols
            elif split_mode == "size":
                tiles = ImageLoader.split_by_tile_size(img, tile_width, tile_height)
                img_width, _ = img.size
                cols = img_width // tile_width
            else:
                raise BatchProcessingError(f"Invalid split mode: {split_mode}")
            
            # Filter tiles by selected positions
            if selected_positions is not None:
                filtered_tiles = []
                for row, col in selected_positions:
                    tile_idx = row * cols + col
                    if tile_idx < len(tiles):
                        filtered_tiles.append(tiles[tile_idx])
                tiles = filtered_tiles
            
            if not tiles:
                raise BatchProcessingError("No tiles generated after filtering")
            
            # Create temporary material manager with tiles
            temp_material_manager = MaterialManager()
            source_filename = Path(image_path).stem
            
            for i, tile in enumerate(tiles):
                tile_name = f"{source_filename}_tile_{i}"
                temp_material_manager.add_material(tile, tile_name)
            
            # Validate template compatibility and apply based on format
            is_multi_template = (
                template.get("format") == "multi_timeline" or (
                    "timelines" in template and "timebase" in template
                )
            )

            if is_multi_template:
                # For multi-timeline templates, ensure we have enough tiles to satisfy
                # the highest referenced material index (0-based contiguous requirement).
                max_index = -1
                timelines = template.get("timelines", [])
                for tl in timelines:
                    for fr in tl.get("frames", []):
                        if isinstance(fr, dict):
                            mi = fr.get("material_index")
                            if isinstance(mi, int) and mi > max_index:
                                max_index = mi
                required_count = max_index + 1 if max_index >= 0 else 0
                if len(temp_material_manager) <= max_index:
                    raise BatchProcessingError(
                        f"Template references material index up to {max_index}, "
                        f"but only {len(temp_material_manager)} tiles were generated"
                    )
                multi_editor, settings = TemplateManager.apply_multi_template(template)
            else:
                # Legacy layered template: validate by material_count setting
                template_settings = template.get("settings", {})
                required_materials = template_settings.get("material_count", 0)
                if len(temp_material_manager) < required_materials:
                    raise BatchProcessingError(
                        f"Template requires {required_materials} materials, "
                        f"but only {len(temp_material_manager)} tiles were generated"
                    )
                layered_sequence_editor, settings = TemplateManager.apply_template(template)

            # Create GIF builder with template settings
            gif_builder = GifBuilder()
            gif_builder.set_output_size(
                settings.get("output_width", 256),
                settings.get("output_height", 256)
            )
            gif_builder.set_loop(settings.get("loop_count", 0))
            gif_builder.set_color_count(color_count)
            
            # Handle transparent background
            if settings.get("transparent_bg", False):
                gif_builder.set_background_color(0, 0, 0, 0)
            else:
                gif_builder.set_background_color(255, 255, 255, 255)
            
            # Determine output path
            if output_path is None:
                source_path = Path(image_path)
                output_path = str(source_path.with_suffix('.gif'))
            
            # Build and save GIF
            if is_multi_template:
                gif_builder.build_from_multitimeline(
                    multi_editor,
                    temp_material_manager,
                    output_path
                )
            else:
                gif_builder.build_from_layered_sequence(
                    layered_sequence_editor.get_frames(),
                    temp_material_manager,
                    output_path
                )
            
            return output_path
            
        except Exception as e:
            raise BatchProcessingError(f"Failed to process {Path(image_path).name}: {str(e)}")
    
    def process_batch(
        self,
        image_paths: List[str],
        template: Dict[str, Any],
        split_mode: str,
        split_rows: int = 4,
        split_cols: int = 4,
        tile_width: int = 32,
        tile_height: int = 32,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
        output_directory: Optional[str] = None,
        color_count: int = 256
    ) -> Tuple[List[str], List[str]]:
        """
        Process multiple images in batch
        
        Args:
            image_paths: List of source image paths
            template: Template dictionary
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid mode
            split_cols: Number of columns for grid mode
            tile_width: Tile width for size mode
            tile_height: Tile height for size mode
            selected_positions: List of (row, col) positions to keep, None = all
            output_directory: Output directory, None = same as source
            color_count: Number of colors in the palette (256, 128, 64, 32, 16)
        
        Returns:
            Tuple of (successful_outputs, failed_images)
            - successful_outputs: List of generated GIF paths
            - failed_images: List of (image_path, error_message) tuples
        """
        successful_outputs = []
        failed_images = []
        total = len(image_paths)
        
        for i, image_path in enumerate(image_paths):
            try:
                self._report_progress(i, total, f"Processing: {Path(image_path).name}")
                
                # Determine output path
                if output_directory:
                    output_path = str(Path(output_directory) / Path(image_path).with_suffix('.gif').name)
                else:
                    output_path = None  # Will use same directory as source
                
                # Process single image
                result_path = self.process_single_image(
                    image_path=image_path,
                    template=template,
                    split_mode=split_mode,
                    split_rows=split_rows,
                    split_cols=split_cols,
                    tile_width=tile_width,
                    tile_height=tile_height,
                    selected_positions=selected_positions,
                    output_path=output_path,
                    color_count=color_count
                )
                
                successful_outputs.append(result_path)
                
            except BatchProcessingError as e:
                failed_images.append((image_path, str(e)))
            except Exception as e:
                failed_images.append((image_path, f"Unexpected error: {str(e)}"))
        
        self._report_progress(total, total, "Batch processing complete")
        
        return successful_outputs, failed_images
    
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
        selected_positions: Optional[List[Tuple[int, int]]] = None
    ) -> Tuple[bool, str]:
        """
        Validate if template is compatible with the split settings
        
        Args:
            template: Template dictionary
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid mode
            split_cols: Number of columns for grid mode
            tile_width: Tile width for size mode
            tile_height: Tile height for size mode
            image_width: Sample image width
            image_height: Sample image height
            selected_positions: List of (row, col) positions to keep
        
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        # Calculate expected tile count
        if split_mode == "grid":
            total_tiles = split_rows * split_cols
            cols = split_cols
        elif split_mode == "size":
            cols = image_width // tile_width
            rows = image_height // tile_height
            total_tiles = rows * cols
        else:
            return False, f"Invalid split mode: {split_mode}"
        
        # Filter by selected positions
        if selected_positions is not None:
            actual_tile_count = 0
            for row, col in selected_positions:
                tile_idx = row * cols + col
                if tile_idx < total_tiles:
                    actual_tile_count += 1
            tile_count = actual_tile_count
        else:
            tile_count = total_tiles
        
        # Check template requirements
        template_settings = template.get("settings", {})
        required_materials = template_settings.get("material_count", 0)
        
        if tile_count < required_materials:
            return False, (
                f"Template requires {required_materials} materials, "
                f"but split will generate only {tile_count} tiles"
            )
        
        return True, f"Compatible: {tile_count} tiles will be generated"

