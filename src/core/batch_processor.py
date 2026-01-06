"""
Batch processor for GIF creation from multiple images
"""
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path
from PIL import Image
from .image_loader import ImageLoader, MaterialManager
from .gif_builder import GifBuilder
from .template_manager import TemplateManager

class BatchProcessingError(Exception):
    """Exception raised during batch processing"""
    pass

class BatchProcessor:
    """
    Handles batch processing of images into GIFs using templates
    """
    
    def __init__(self):
        """Initialize batch processor"""
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set progress callback function
        
        Args:
            callback: Function(current, total, status_message) to report progress
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
        split_rows: int,
        split_cols: int,
        tile_width: int,
        tile_height: int,
        color_count: int = 256,
        output_path: Optional[str] = None,
        selected_positions: Optional[List[Tuple[int, int]]] = None,
        output_width: Optional[int] = None,
        output_height: Optional[int] = None
    ) -> str:
        """
        Process a single image into a GIF using a template
        
        Args:
            image_path: Path to source image
            template: Template dictionary with animation structure
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid split
            split_cols: Number of columns for grid split
            tile_width: Tile width for size split
            tile_height: Tile height for size split
            color_count: Number of colors in output GIF (2-256)
            output_path: Optional output path. If None, uses source path with .gif extension
            selected_positions: Optional list of (row, col) tuples for tile selection
            output_width: Optional output width. If None, uses template setting or default
            output_height: Optional output height. If None, uses template setting or default
            
        Returns:
            Path to created GIF file
            
        Raises:
            BatchProcessingError: If processing fails
        """
        try:
            # Load and cut image into tiles
            image = ImageLoader.load_image(image_path)
            
            if split_mode == "grid":
                tiles = ImageLoader.split_into_tiles(image, split_rows, split_cols)
            else:  # size mode
                tiles = ImageLoader.split_by_tile_size(image, tile_width, tile_height)
            
            # Filter tiles if selection provided
            if selected_positions:
                if split_mode == "grid":
                    cols = split_cols
                else:
                    cols = image.size[0] // tile_width
                
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
                template.get("format") == "multi_timeline" or
                template.get("format") == "layer_timeline" or
                ("timelines" in template and "timebase" in template) or
                ("layer_tracks" in template and "timebase" in template)
            )

            if is_multi_template:
                # For multi-timeline templates, ensure we have enough tiles
                max_index = -1
                timelines = template.get("timelines", [])
                for tl in timelines:
                    for fr in tl.get("frames", []):
                        if isinstance(fr, dict):
                            mi = fr.get("material_index")
                            if isinstance(mi, int) and mi > max_index:
                                max_index = mi
                
                # Also check layer_tracks
                layer_tracks = template.get("layer_tracks", [])
                for track in layer_tracks:
                    for frame in track.get("frames", []):
                        if isinstance(frame, dict):
                            mi = frame.get("material_index")
                            if isinstance(mi, int) and mi > max_index:
                                max_index = mi
                
                required_count = max_index + 1 if max_index >= 0 else 0
                if len(temp_material_manager) < required_count:
                    raise BatchProcessingError(
                        f"Template requires {required_count} materials, "
                        f"but only {len(temp_material_manager)} tiles were generated"
                    )
                
                multi_editor, group_manager, settings = TemplateManager.apply_layer_timeline_template(
                    template, 
                    max_material_index=len(temp_material_manager)
                )
            else:
                # Legacy layered template
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
            
            # Use explicit output size if provided, otherwise use template settings or defaults
            final_width = output_width if output_width is not None else settings.get("output_width", 256)
            final_height = output_height if output_height is not None else settings.get("output_height", 256)
            
            gif_builder.set_output_size(final_width, final_height)
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
                gif_builder.build_from_layer_timeline(
                    multi_editor,
                    temp_material_manager,
                    group_manager,
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
            import traceback
            error_msg = f"Failed to process {Path(image_path).name}: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            raise BatchProcessingError(error_msg)
    
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
        output_height: Optional[int] = None
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Process multiple images into GIFs using the same template
        
        Args:
            image_paths: List of paths to source images
            template: Template dictionary with animation structure
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid split
            split_cols: Number of columns for grid split
            tile_width: Tile width for size split
            tile_height: Tile height for size split
            color_count: Number of colors in output GIF (2-256)
            output_directory: Optional output directory. If None, outputs alongside source images
            selected_positions: Optional list of (row, col) tuples for tile selection
            output_width: Optional output width. If None, uses template setting or default
            output_height: Optional output height. If None, uses template setting or default
            
        Returns:
            Tuple of (successful_paths, failed_items)
            failed_items is a list of (image_path, error_message) tuples
        """
        successful = []
        failed = []
        total = len(image_paths)
        
        for idx, image_path in enumerate(image_paths, 1):
            try:
                self._report_progress(idx, total, f"Processing {Path(image_path).name}")
                
                # Determine output path
                if output_directory:
                    output_path = str(Path(output_directory) / f"{Path(image_path).stem}.gif")
                else:
                    output_path = None  # Use default (alongside source)
                
                # Process the image
                result_path = self.process_single_image(
                    image_path,
                    template,
                    split_mode,
                    split_rows,
                    split_cols,
                    tile_width,
                    tile_height,
                    color_count,
                    output_path,
                    selected_positions,
                    output_width,
                    output_height
                )
                
                successful.append(result_path)
                self._report_progress(idx, total, f"Completed {Path(image_path).name}")
                
            except Exception as e:
                error_msg = str(e)
                failed.append((image_path, error_msg))
                self._report_progress(idx, total, f"Failed {Path(image_path).name}: {error_msg}")
        
        return successful, failed
    
    @staticmethod
    def validate_template(template: Dict[str, Any]) -> bool:
        """
        Validate that a template has the required structure
        
        Args:
            template: Template dictionary to validate
            
        Returns:
            True if template is valid
            
        Raises:
            ValueError: If template structure is invalid
        """
        if not isinstance(template, dict):
            raise ValueError("Template must be a dictionary")
        
        # Check for version
        if "version" not in template:
            raise ValueError("Template missing 'version' field")
        
        # Check format type
        format_type = template.get("format", "layered")
        
        if format_type in ("multi_timeline", "layer_timeline"):
            # New format validation
            if "timebase" not in template:
                raise ValueError("Multi-timeline template missing 'timebase'")
            
            # Check for either timelines or layer_tracks
            has_timelines = "timelines" in template
            has_layer_tracks = "layer_tracks" in template
            
            if not has_timelines and not has_layer_tracks:
                raise ValueError("Multi-timeline template missing 'timelines' or 'layer_tracks'")
            
            if has_layer_tracks:
                if not isinstance(template["layer_tracks"], list):
                    raise ValueError("'layer_tracks' must be a list")
                for track in template["layer_tracks"]:
                    if "frames" not in track:
                        raise ValueError("Layer track missing 'frames' field")
                        
            if has_timelines:
                if not isinstance(template["timelines"], list):
                    raise ValueError("'timelines' must be a list")
                for timeline in template["timelines"]:
                    if "frames" not in timeline:
                        raise ValueError("Timeline missing 'frames' field")
        else:
            # Legacy format validation
            if "frames" not in template:
                raise ValueError("Template missing 'frames' field")
            
            if "settings" not in template:
                raise ValueError("Template missing 'settings' field")
        
        return True
    
    @staticmethod
    def estimate_required_tiles(template: Dict[str, Any]) -> int:
        """
        Estimate the number of tiles required by a template
        
        Args:
            template: Template dictionary
            
        Returns:
            Maximum material index + 1 (number of required tiles)
        """
        max_index = -1
        
        format_type = template.get("format", "layered")
        
        if format_type in ("multi_timeline", "layer_timeline"):
            # Check timelines
            timelines = template.get("timelines", [])
            for timeline in timelines:
                for frame in timeline.get("frames", []):
                    if isinstance(frame, dict):
                        mat_idx = frame.get("material_index")
                        if isinstance(mat_idx, int) and mat_idx > max_index:
                            max_index = mat_idx
            
            # Check layer_tracks
            layer_tracks = template.get("layer_tracks", [])
            for track in layer_tracks:
                for frame in track.get("frames", []):
                    if isinstance(frame, dict):
                        mat_idx = frame.get("material_index")
                        if isinstance(mat_idx, int) and mat_idx > max_index:
                            max_index = mat_idx
        else:
            # Legacy format
            frames = template.get("frames", [])
            for frame in frames:
                if isinstance(frame, dict):
                    for layer in frame.get("layers", []):
                        mat_idx = layer.get("material_index")
                        if isinstance(mat_idx, int) and mat_idx > max_index:
                            max_index = mat_idx
        
        return max_index + 1 if max_index >= 0 else 0
    
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
        Validate that a template is compatible with the batch processing settings
        
        Args:
            template: Template dictionary to validate
            split_mode: "grid" or "size"
            split_rows: Number of rows for grid split
            split_cols: Number of columns for grid split
            tile_width: Tile width for size split
            tile_height: Tile height for size split
            image_width: Source image width
            image_height: Source image height
            selected_positions: Optional list of selected tile positions
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            # First validate template structure
            try:
                BatchProcessor.validate_template(template)
            except ValueError as e:
                return False, f"Invalid template structure: {str(e)}"
            
            # Calculate number of tiles that will be generated
            if split_mode == "grid":
                total_tiles = split_rows * split_cols
            else:  # size mode
                cols = image_width // tile_width
                rows = image_height // tile_height
                total_tiles = rows * cols
            
            # If positions are selected, count only those
            if selected_positions:
                available_tiles = len(selected_positions)
            else:
                available_tiles = total_tiles
            
            if available_tiles == 0:
                return False, "No tiles will be generated with current settings"
            
            # Check if template requires more materials than available
            required_tiles = BatchProcessor.estimate_required_tiles(template)
            
            if required_tiles > available_tiles:
                return False, (
                    f"Template requires {required_tiles} materials, "
                    f"but only {available_tiles} tiles will be generated. "
                    f"Please adjust split settings or select more tile positions."
                )
            
            return True, (
                f"✓ Template compatible: requires {required_tiles} materials, "
                f"{available_tiles} tiles will be generated"
            )
            
        except Exception as e:
            return False, f"Validation failed: {str(e)}"
