from typing import List, Tuple, Optional
from pathlib import Path
from PIL import Image
from .utils import create_background, paste_center, ensure_rgba
from .sequence_editor import SequenceEditor, Frame
from .image_loader import MaterialManager
from .layer_system import LayeredFrame, LayerCompositor
from .layer_timeline import LayerTimelineEditor


class GifBuilder:
    
    def __init__(self):
        self.output_size: Optional[Tuple[int, int]] = None
        self.background_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
        self.loop: int = 0
        self.optimize: bool = True
        self.disposal: int = 2
        self.color_count: int = 256  # Default color palette size
        self.chroma_key_color: Optional[Tuple[int, int, int]] = None  # RGB color to make transparent
        self.chroma_key_threshold: int = 30  # Color similarity threshold (0-255)
    
    def set_output_size(self, width: int, height: int):
        self.output_size = (width, height)
    
    def set_background_color(self, r: int, g: int, b: int, a: int = 255):
        self.background_color = (r, g, b, a)
    
    def set_loop(self, loop: int):
        self.loop = loop
    
    def set_color_count(self, color_count: int):
        """Set the number of colors in the palette (256, 128, 64, 32, 16, etc.)"""
        self.color_count = color_count
    
    def set_chroma_key(self, r: int, g: int, b: int, threshold: int = 30):
        """Set a color to be made transparent (chroma key/green screen effect)
        
        Args:
            r, g, b: RGB values of the color to make transparent
            threshold: Color similarity threshold (0-255). Higher values will make more similar colors transparent.
        """
        self.chroma_key_color = (r, g, b)
        self.chroma_key_threshold = threshold
    
    def clear_chroma_key(self):
        """Remove chroma key effect"""
        self.chroma_key_color = None
    
    def apply_chroma_key(self, image: Image.Image) -> Image.Image:
        """Apply chroma key effect to an image, making specified color transparent
        
        Args:
            image: Input image
            
        Returns:
            Image with chroma key applied (RGBA format)
        """
        if self.chroma_key_color is None:
            return ensure_rgba(image)
        
        img = ensure_rgba(image)
        width, height = img.size
        
        target_r, target_g, target_b = self.chroma_key_color
        threshold = self.chroma_key_threshold
        
        # Create a copy to modify
        result = img.copy()
        result_pixels = result.load()
        
        # Make similar colors transparent
        for y in range(height):
            for x in range(width):
                r, g, b, _ = result_pixels[x, y]
                
                # Calculate color distance (Euclidean distance in RGB space)
                color_dist = ((r - target_r) ** 2 + (g - target_g) ** 2 + (b - target_b) ** 2) ** 0.5
                
                # If color is within threshold, make it transparent
                if color_dist <= threshold:
                    result_pixels[x, y] = (r, g, b, 0)
        
        return result
    
    def prepare_frame(self, material_image: Image.Image) -> Image.Image:
        img = ensure_rgba(material_image)
        
        if self.output_size:
            # If transparent background, don't create a background image
            if self.background_color[3] == 0:
                # Just resize if needed, keep transparency
                if img.size[0] > self.output_size[0] or img.size[1] > self.output_size[1]:
                    img.thumbnail(self.output_size, Image.Resampling.LANCZOS)
                
                # Create a transparent background of the output size
                transparent_bg = Image.new('RGBA', self.output_size, (0, 0, 0, 0))
                result = paste_center(transparent_bg, img)
                return result
            else:
                # Create solid background
                background = create_background(self.output_size, self.background_color)
                
                if img.size[0] > self.output_size[0] or img.size[1] > self.output_size[1]:
                    img.thumbnail(self.output_size, Image.Resampling.LANCZOS)
                
                result = paste_center(background, img)
                return result
        else:
            return img
    
    def build_from_sequence(
        self,
        material_manager: MaterialManager,
        sequence_editor: SequenceEditor,
        output_path: str
    ):
        if len(sequence_editor) == 0:
            raise ValueError("Sequence is empty, cannot generate GIF")
        
        if len(material_manager) == 0:
            raise ValueError("Material list is empty, cannot generate GIF")
        
        frames = []
        durations = []
        
        for frame in sequence_editor.get_frames():
            material = material_manager.get_material(frame.material_index)
            if material is None:
                raise ValueError(f"Material index {frame.material_index} does not exist")
            
            material_img, _ = material
            frame_img = self.prepare_frame(material_img)
            
            # Convert RGBA to appropriate format for GIF
            if frame_img.mode == 'RGBA':
                if self.background_color[3] == 0:
                    # For transparent background, properly handle alpha channel
                    # Split alpha channel
                    alpha = frame_img.split()[3]
                    
                    # Create a mask for transparent pixels (alpha < 128)
                    # Pixels with alpha >= 128 are considered opaque
                    frame_img = frame_img.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE, colors=self.color_count-1)
                    
                    # Set transparent pixels based on alpha channel
                    # Find a color index to use for transparency
                    mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
                    
                    # Paste the palette image on a transparent background
                    # This ensures truly transparent pixels are marked correctly
                    frame_img.paste(255, mask)
                    frame_img.info['transparency'] = 255
                else:
                    # For solid background, composite with background color
                    rgb_bg = Image.new('RGB', frame_img.size, self.background_color[:3])
                    rgb_bg.paste(frame_img, mask=frame_img.split()[3])
                    frame_img = rgb_bg
            
            frames.append(frame_img)
            durations.append(frame.duration)
        
        self.save_gif(frames, durations, output_path)
    
    def build_from_images(
        self,
        images: List[Image.Image],
        durations: List[int],
        output_path: str
    ):
        if not images:
            raise ValueError("Image list is empty")
        
        if len(images) != len(durations):
            raise ValueError("Image count does not match duration count")
        
        frames = []
        for img in images:
            frame_img = self.prepare_frame(img)
            
            # Convert RGBA to appropriate format for GIF
            if frame_img.mode == 'RGBA':
                if self.background_color[3] == 0:
                    # For transparent background, properly handle alpha channel
                    # Split alpha channel
                    alpha = frame_img.split()[3]
                    
                    # Create a mask for transparent pixels (alpha < 128)
                    # Pixels with alpha >= 128 are considered opaque
                    frame_img = frame_img.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE, colors=self.color_count-1)
                    
                    # Set transparent pixels based on alpha channel
                    # Find a color index to use for transparency
                    mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
                    
                    # Paste the palette image on a transparent background
                    # This ensures truly transparent pixels are marked correctly
                    frame_img.paste(255, mask)
                    frame_img.info['transparency'] = 255
                else:
                    # For solid background, composite with background color
                    rgb_bg = Image.new('RGB', frame_img.size, self.background_color[:3])
                    rgb_bg.paste(frame_img, mask=frame_img.split()[3])
                    frame_img = rgb_bg
            
            frames.append(frame_img)
        
        self.save_gif(frames, durations, output_path)
    
    def save_gif(self, frames: List[Image.Image], durations: List[int], output_path: str):
        if not frames:
            raise ValueError("Frame list is empty")
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        save_kwargs = {
            'format': 'GIF',
            'save_all': True,
            'append_images': frames[1:],
            'duration': durations,
            'loop': self.loop,
            'optimize': self.optimize,
            'disposal': self.disposal
        }
        
        if self.background_color[3] == 0:
            # For transparent GIF, set disposal method to clear to background
            save_kwargs['disposal'] = 2
        
        frames[0].save(output_path, **save_kwargs)
    
    def resize_gif(self, input_path: str, output_path: str, scale_factor: float = 0.5):
        """
        Resize an existing GIF file
        
        Args:
            input_path: Path to input GIF file
            output_path: Path for output GIF file
            scale_factor: Scale factor (0.5 = half size, 2.0 = double size)
        """
        try:
            with Image.open(input_path) as gif:
                # Get all frames
                frames = []
                durations = []
                
                # Get loop count from original GIF
                loop = 0
                if 'loop' in gif.info:
                    loop = gif.info['loop']
                
                # Extract frames
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    frame = gif.copy()
                    
                    # Resize frame
                    new_size = (
                        int(frame.width * scale_factor),
                        int(frame.height * scale_factor)
                    )
                    resized_frame = frame.resize(new_size, Image.Resampling.LANCZOS)
                    
                    frames.append(resized_frame)
                    
                    # Get duration
                    duration = gif.info.get('duration', 100)  # Default 100ms
                    durations.append(duration)
                
                # Save resized GIF
                if frames:
                    save_kwargs = {
                        'format': 'GIF',
                        'save_all': True,
                        'append_images': frames[1:],
                        'duration': durations,
                        'loop': loop,
                        'optimize': True,
                        'disposal': 2
                    }
                    
                    frames[0].save(output_path, **save_kwargs)
                    
        except Exception as e:
            raise ValueError(f"Failed to resize GIF: {str(e)}")
    
    def get_gif_info(self, gif_path: str) -> dict:
        """
        Get information about a GIF file
        
        Args:
            gif_path: Path to GIF file
        
        Returns:
            Dictionary with GIF information
        """
        try:
            with Image.open(gif_path) as gif:
                frames = []
                total_duration = 0
                
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    frame = gif.copy()
                    frames.append(frame)
                    
                    duration = gif.info.get('duration', 100)
                    total_duration += duration
                
                return {
                    'frame_count': gif.n_frames,
                    'size': (gif.width, gif.height),
                    'total_duration_ms': total_duration,
                    'loop': gif.info.get('loop', 0),
                    'mode': gif.mode,
                    'has_transparency': 'transparency' in gif.info,
                    'file_size_bytes': Path(gif_path).stat().st_size
                }
                
        except Exception as e:
            raise ValueError(f"Failed to read GIF info: {str(e)}")
    
    def get_preview_frames(
        self,
        material_manager: MaterialManager,
        sequence_editor: SequenceEditor
    ) -> List[Tuple[Image.Image, int]]:
        frames = []
        
        for frame in sequence_editor.get_frames():
            material = material_manager.get_material(frame.material_index)
            if material is None:
                continue
            
            material_img, _ = material
            frame_img = self.prepare_frame(material_img)
            
            frames.append((frame_img, frame.duration))
        
        return frames
    
    def prepare_layered_frame(
        self,
        layered_frame: LayeredFrame,
        material_manager: MaterialManager
    ) -> Image.Image:
        """
        Prepare a layered frame by compositing all layers
        
        Args:
            layered_frame: The layered frame to composite
            material_manager: MaterialManager to get source images
        
        Returns:
            Composited image
        """
        if not self.output_size:
            # Default to first layer's size if output size not set
            if layered_frame.layers and len(layered_frame.layers) > 0:
                first_layer = layered_frame.layers[0]
                material = material_manager.get_material(first_layer.material_index)
                if material:
                    img, _ = material
                    self.output_size = img.size
        
        # Use transparent background for layered frames by default
        bg_color = self.background_color if self.background_color[3] > 0 else (0, 0, 0, 0)
        
        # Composite the frame
        composited = LayerCompositor.composite_frame(
            layered_frame,
            material_manager,
            self.output_size,
            bg_color
        )
        
        return composited
    
    def build_from_layered_sequence(
        self,
        layered_frames: List[LayeredFrame],
        material_manager: MaterialManager,
        output_path: str
    ):
        """
        Build GIF from a sequence of layered frames
        
        Args:
            layered_frames: List of layered frames
            material_manager: MaterialManager to get source images
            output_path: Output file path
        """
        if not layered_frames:
            raise ValueError("Layered frame sequence is empty")
        
        frames = []
        durations = []
        
        for layered_frame in layered_frames:
            # Composite the layered frame
            composited = self.prepare_layered_frame(layered_frame, material_manager)
            
            # Convert RGBA to appropriate format for GIF
            if composited.mode == 'RGBA':
                if self.background_color[3] == 0:
                    # For transparent background, properly handle alpha channel
                    # Split alpha channel
                    alpha = composited.split()[3]
                    
                    # Create a mask for transparent pixels (alpha < 128)
                    # Pixels with alpha >= 128 are considered opaque
                    composited = composited.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE, colors=self.color_count-1)
                    
                    # Set transparent pixels based on alpha channel
                    # Find a color index to use for transparency
                    mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
                    
                    # Paste the palette image on a transparent background
                    # This ensures truly transparent pixels are marked correctly
                    composited.paste(255, mask)
                    composited.info['transparency'] = 255
                else:
                    # For solid background, composite with background color
                    rgb_bg = Image.new('RGB', composited.size, self.background_color[:3])
                    rgb_bg.paste(composited, mask=composited.split()[3])
                    composited = rgb_bg
            
            frames.append(composited)
            durations.append(layered_frame.duration)
        
        self.save_gif(frames, durations, output_path)
    
    def get_layered_preview_frames(
        self,
        layered_frames: List[LayeredFrame],
        material_manager: MaterialManager
    ) -> List[Tuple[Image.Image, int]]:
        """
        Get preview frames from layered frames
        
        Args:
            layered_frames: List of layered frames
            material_manager: MaterialManager to get source images
        
        Returns:
            List of (image, duration) tuples for preview
        """
        frames = []
        
        for layered_frame in layered_frames:
            composited = self.prepare_layered_frame(layered_frame, material_manager)
            frames.append((composited, layered_frame.duration))
        
        return frames

    # ----- Layer timeline composition -----
    def _expand_timeline_with_groups(
        self,
        editor: LayerTimelineEditor,
        group_manager
    ) -> Tuple[List[List[Tuple[Optional[int], int, int]]], List[int]]:
        """
        Expand timeline with groups into a flat frame list.
        
        Each timebase frame that contains groups will be expanded into multiple sub-frames.
        All layers are synchronized so each timebase frame expands to the same number of sub-frames.
        
        Args:
            editor: LayerTimelineEditor instance
            group_manager: GroupManager instance
        
        Returns:
            (expanded_frames, expanded_durations)
            - expanded_frames: List of frames, each frame is a list of (material_idx, x, y) tuples (one per layer)
            - expanded_durations: List of durations for each expanded frame (in ms)
        """
        if group_manager is None:
            # No groups, return as-is
            timebase_count = editor.get_frame_count()
            expanded_frames = []
            expanded_durations = []
            
            for i in range(timebase_count):
                frame_layers = []
                for mat_idx, grp_idx, x, y in editor.iter_frame_layers(i):
                    if mat_idx is not None:
                        frame_layers.append((mat_idx, x, y))
                expanded_frames.append(frame_layers)
                expanded_durations.append(editor.durations_ms[i] if i < len(editor.durations_ms) else 100)
            
            return expanded_frames, expanded_durations
        
        timebase_count = editor.get_frame_count()
        expanded_frames = []
        expanded_durations = []
        
        # Process each timebase frame
        for timebase_idx in range(timebase_count):
            # For each timebase frame, determine the maximum expansion factor across all layers
            max_expansion = 1
            layer_expansions = []  # List of (track_index, expansion_info)
            
            for track_idx, track in enumerate(editor.layer_tracks):
                if timebase_idx >= len(track.frames):
                    layer_expansions.append((track_idx, None, 1))
                    continue
                
                frame = track.frames[timebase_idx]
                
                if frame.group_index is not None:
                    group = group_manager.get_group(frame.group_index)
                    if group is not None and len(group.material_indices) > 0:
                        expansion_count = group.get_total_frames()
                        max_expansion = max(max_expansion, expansion_count)
                        layer_expansions.append((track_idx, group, expansion_count))
                    else:
                        layer_expansions.append((track_idx, None, 1))
                elif frame.material_index is not None:
                    layer_expansions.append((track_idx, None, 1))
                else:
                    # Empty frame
                    layer_expansions.append((track_idx, None, 1))
            
            # Calculate duration for each sub-frame
            timebase_duration = editor.durations_ms[timebase_idx] if timebase_idx < len(editor.durations_ms) else 100
            
            # Expand this timebase frame into sub-frames
            for sub_frame_idx in range(max_expansion):
                sub_frame_layers = []
                
                for track_idx, group, expansion_count in layer_expansions:
                    track = editor.layer_tracks[track_idx]
                    if timebase_idx >= len(track.frames):
                        continue
                    
                    frame = track.frames[timebase_idx]
                    
                    if group is not None:
                        # Skip empty groups (all materials filtered out)
                        if len(group.material_indices) == 0:
                            continue
                        
                        # Expand the group - cycle through materials if max_expansion > expansion_count
                        material_idx_in_group = sub_frame_idx % len(group.material_indices)
                        material_idx = group.material_indices[material_idx_in_group]
                        x = frame.x + track.offset_x
                        y = frame.y + track.offset_y
                        
                        # Apply independent offset if group has independent_offsets enabled
                        if group.independent_offsets:
                            offset_x, offset_y = group.get_material_offset(material_idx_in_group)
                            x += offset_x
                            y += offset_y
                        
                        sub_frame_layers.append((material_idx, x, y))
                        
                        # Use group's frame duration
                        if sub_frame_idx == 0:
                            # First sub-frame of this expansion
                            sub_frame_duration = group.frame_duration
                    elif frame.material_index is not None:
                        # Single material - repeat it for all sub-frames
                        material_idx = frame.material_index
                        x = frame.x + track.offset_x
                        y = frame.y + track.offset_y
                        sub_frame_layers.append((material_idx, x, y))
                
                expanded_frames.append(sub_frame_layers)
                
                # For duration, prioritize group's frame_duration over timebase duration
                # Check if any layer in this timebase frame has a group
                group_duration = None
                for _, group, _ in layer_expansions:
                    if group is not None:
                        group_duration = group.frame_duration
                        break
                
                if group_duration is not None:
                    # Use group's frame_duration (even if there's only 1 material)
                    expanded_durations.append(group_duration)
                elif max_expansion > 1:
                    # Multiple expansions but no group - divide timebase duration
                    expanded_durations.append(timebase_duration // max_expansion)
                else:
                    # Single frame, no group - use timebase duration
                    expanded_durations.append(timebase_duration)
        
        return expanded_frames, expanded_durations
    
    def _compose_from_expanded_frame(
        self,
        frame_layers: List[Tuple[Optional[int], int, int]],
        material_manager: MaterialManager
    ) -> Image.Image:
        """
        Composite one output frame from expanded frame layers.
        
        Args:
            frame_layers: List of (material_idx, x, y) tuples for this frame
            material_manager: MaterialManager instance
        
        Returns:
            Composited image
        """
        # Use pre-set output_size or auto-detect
        if self.output_size is None:
            # Auto-detect from first material
            for material_idx, _, _ in frame_layers:
                if material_idx is not None:
                    material = material_manager.get_material(material_idx)
                    if material is not None:
                        img, _ = material
                        self.output_size = img.size
                        break
            
            if self.output_size is None:
                # Fallback
                self.output_size = (400, 400)
        
        bg_color = self.background_color if self.background_color[3] > 0 else (0, 0, 0, 0)
        canvas = Image.new('RGBA', self.output_size, bg_color)
        
        # Bottom to top
        for material_idx, x, y in frame_layers:
            if material_idx is None:
                continue
            
            material = material_manager.get_material(material_idx)
            if material is None:
                continue
            
            material_img, _ = material
            img_rgba = ensure_rgba(material_img)
            
            # Apply chroma key if set
            if self.chroma_key_color is not None:
                img_rgba = self.apply_chroma_key(img_rgba)
            
            try:
                canvas.paste(img_rgba, (x, y), img_rgba)
            except Exception:
                # Skip paste failures (out of bounds etc.)
                pass
        
        return canvas
    
    def _compose_from_layer_timeline_frame(
        self,
        editor: LayerTimelineEditor,
        material_manager: MaterialManager,
        group_manager,  # GroupManager instance
        frame_index: int
    ) -> Image.Image:
        """Composite one output frame from all layer tracks at the given frame index."""
        # Only auto-detect output size if it's None (not set at all)
        if self.output_size is None:
            for material_idx, group_idx, _, _ in editor.iter_frame_layers(frame_index):
                if material_idx is not None:
                    material = material_manager.get_material(material_idx)
                    if material is not None:
                        img, _ = material
                        self.output_size = img.size
                        break
                elif group_idx is not None and group_manager is not None:
                    group = group_manager.get_group(group_idx)
                    if group is not None and len(group.material_indices) > 0:
                        material = material_manager.get_material(group.material_indices[0])
                        if material is not None:
                            img, _ = material
                            self.output_size = img.size
                            break
        
        if self.output_size is None:
            # Fallback
            self.output_size = (400, 400)

        bg_color = self.background_color if self.background_color[3] > 0 else (0, 0, 0, 0)
        canvas = Image.new('RGBA', self.output_size, bg_color)

        # Bottom to top
        for material_idx, group_idx, x, y in editor.iter_frame_layers(frame_index):
            # Handle group reference
            if group_idx is not None and group_manager is not None:
                group = group_manager.get_group(group_idx)
                if group is None:
                    continue
                
                # For preview, render first material only (simplified view)
                # Apply independent offset if set
                if len(group.material_indices) > 0:
                    material_idx = group.material_indices[0]
                    # Apply independent offset for first material (index 0)
                    if group.independent_offsets:
                        offset_x, offset_y = group.get_material_offset(0)
                        x += offset_x
                        y += offset_y
                else:
                    continue
            
            # Handle material reference
            if material_idx is None:
                continue
                
            material = material_manager.get_material(material_idx)
            if material is None:
                continue
            material_img, _ = material
            img_rgba = ensure_rgba(material_img)
            
            # Apply chroma key if set
            if self.chroma_key_color is not None:
                img_rgba = self.apply_chroma_key(img_rgba)
            
            try:
                canvas.paste(img_rgba, (x, y), img_rgba)
            except Exception:
                # Skip paste failures (out of bounds etc.)
                pass

        return canvas

    def get_layer_timeline_preview_frames(
        self,
        editor: LayerTimelineEditor,
        material_manager: MaterialManager,
        group_manager=None
    ) -> List[Tuple[Image.Image, int]]:
        """Return preview frames (image, duration) for the whole layer timeline with groups expanded."""
        # Expand groups first
        expanded_frames, expanded_durations = self._expand_timeline_with_groups(editor, group_manager)
        
        frames: List[Tuple[Image.Image, int]] = []
        for frame_layers, duration in zip(expanded_frames, expanded_durations):
            composed = self._compose_from_expanded_frame(frame_layers, material_manager)
            frames.append((composed, duration))
        
        return frames

    def build_from_layer_timeline(
        self,
        editor: LayerTimelineEditor,
        material_manager: MaterialManager,
        group_manager=None,
        output_path: str = None
    ):
        """Export a GIF from the layer timeline model with groups expanded."""
        if output_path is None:
            # Handle old calling signature for backward compatibility
            if isinstance(group_manager, str):
                output_path = group_manager
                group_manager = None
        
        if editor.get_frame_count() == 0:
            raise ValueError("Timeline is empty, cannot generate GIF")
        if len(material_manager) == 0:
            raise ValueError("Material list is empty, cannot generate GIF")

        # Expand groups first
        expanded_frames, expanded_durations = self._expand_timeline_with_groups(editor, group_manager)
        
        if not expanded_frames:
            raise ValueError("No frames to export after expanding groups")

        frames: List[Image.Image] = []
        durations: List[int] = []
        
        for frame_layers, duration in zip(expanded_frames, expanded_durations):
            composed = self._compose_from_expanded_frame(frame_layers, material_manager)

            # Convert RGBA similar to layered flow
            if composed.mode == 'RGBA':
                if self.background_color[3] == 0:
                    alpha = composed.split()[3]
                    composed = composed.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE, colors=self.color_count-1)
                    mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
                    composed.paste(255, mask)
                    composed.info['transparency'] = 255
                else:
                    rgb_bg = Image.new('RGB', composed.size, self.background_color[:3])
                    rgb_bg.paste(composed, mask=composed.split()[3])
                    composed = rgb_bg

            frames.append(composed)
            durations.append(duration)

        self.save_gif(frames, durations, output_path)