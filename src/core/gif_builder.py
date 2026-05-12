from typing import List, Tuple, Optional, TYPE_CHECKING
from pathlib import Path
import numpy as np
from PIL import Image
from .utils import create_background, paste_center, ensure_rgba
from .sequence_editor import SequenceEditor, Frame
from .image_loader import MaterialManager
from .layer_system import LayeredFrame, LayerCompositor
from .layer_timeline import LayerTimelineEditor
from .composition_group import (
    CompositionGroup,
    FrameEntry,
    SubGroupEntry,
    LayerBlockEntry,
    FrameSlot,
    GroupSlot,
    is_frame_entry,
    is_sub_group_entry,
    is_layer_block_entry,
    is_frame_slot,
    is_group_slot,
)

if TYPE_CHECKING:
    from .group_manager import GroupManager


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
        """Apply chroma key effect to an image, making specified color transparent.

        Uses NumPy vectorised operations instead of a per-pixel Python loop,
        giving ~100× speed-up on typical image sizes.

        Args:
            image: Input image

        Returns:
            Image with chroma key applied (RGBA format)
        """
        if self.chroma_key_color is None:
            return ensure_rgba(image)

        img = ensure_rgba(image)
        arr = np.array(img, dtype=np.int32)   # shape (H, W, 4)

        tr, tg, tb = self.chroma_key_color
        # Squared Euclidean distance in RGB; compare against threshold²
        dist_sq = (
            (arr[:, :, 0] - tr) ** 2
            + (arr[:, :, 1] - tg) ** 2
            + (arr[:, :, 2] - tb) ** 2
        )
        mask = dist_sq <= (self.chroma_key_threshold ** 2)
        arr[:, :, 3] = np.where(mask, 0, arr[:, :, 3])

        return Image.fromarray(arr.astype(np.uint8), "RGBA")
    
    # ------------------------------------------------------------------
    # Internal helper: convert a single composited RGBA image to the
    # palette/mode required for GIF output.
    # ------------------------------------------------------------------
    def _convert_frame_for_gif(self, img: Image.Image) -> Image.Image:
        """Convert a composited RGBA image to an appropriate mode for GIF saving.

        * Transparent background → palette mode (P) with transparency index 255.
        * Solid background → alpha-composite onto the background colour, return RGB.
        * Non-RGBA input → returned unchanged.

        Args:
            img: Source image (typically RGBA).

        Returns:
            Image ready to be appended to a GIF frame list.
        """
        if img.mode != "RGBA":
            return img

        if self.background_color[3] == 0:
            alpha = img.split()[3]
            out = img.convert("RGB").convert(
                "P", palette=Image.Palette.ADAPTIVE, colors=self.color_count - 1
            )
            mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
            out.paste(255, mask)
            out.info["transparency"] = 255
            return out
        else:
            rgb_bg = Image.new("RGB", img.size, self.background_color[:3])
            rgb_bg.paste(img, mask=img.split()[3])
            return rgb_bg

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
            frames.append(self._convert_frame_for_gif(frame_img))
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
        
        frames = [self._convert_frame_for_gif(self.prepare_frame(img)) for img in images]
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
                total_duration = 0
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    total_duration += gif.info.get("duration", 100)

                return {
                    "frame_count": gif.n_frames,
                    "size": (gif.width, gif.height),
                    "total_duration_ms": total_duration,
                    "loop": gif.info.get("loop", 0),
                    "mode": gif.mode,
                    "has_transparency": "transparency" in gif.info,
                    "file_size_bytes": Path(gif_path).stat().st_size,
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
            
            frames.append(self._convert_frame_for_gif(composited))
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
            frames.append(self._convert_frame_for_gif(composed))
            durations.append(duration)

        self.save_gif(frames, durations, output_path)

    # ----- Composition group (group-led) expansion and build -----

    def _expand_composition_group(
        self,
        group_id: int,
        group_manager: "GroupManager",
        material_manager: MaterialManager,
    ) -> Tuple[List[List[Tuple[Optional[int], int, int]]], List[int]]:
        """
        Expand a CompositionGroup into a flat list of (frame_layers, duration).
        Each frame is a list of (material_idx, x, y) to composite.

        Args:
            group_id: Index of the group in group_manager
            group_manager: GroupManager holding CompositionGroups
            material_manager: For resolving materials (not used for expansion, only for composition)

        Returns:
            (expanded_frames, expanded_durations)
        """
        group = group_manager.get_group(group_id)
        if group is None:
            return [], []

        expanded_frames: List[List[Tuple[Optional[int], int, int]]] = []
        expanded_durations: List[int] = []
        default_dur = group.default_duration_ms

        for entry in group.entries:
            if is_frame_entry(entry):
                e = entry  # type: FrameEntry
                expanded_frames.append([(e.material_index, e.x, e.y)])
                expanded_durations.append(e.duration_ms if e.duration_ms is not None else default_dur)

            elif is_sub_group_entry(entry):
                e = entry  # type: SubGroupEntry
                sub_frames, sub_durations = self._expand_composition_group(
                    e.group_id, group_manager, material_manager
                )
                # Apply this entry's x/y offset to every layer in every frame
                if e.x != 0 or e.y != 0:
                    sub_frames = [
                        [(m, px + e.x, py + e.y) for m, px, py in frame]
                        for frame in sub_frames
                    ]
                # Apply per-reference duration override
                if e.duration_override_ms is not None:
                    sub_durations = [e.duration_override_ms] * len(sub_durations)
                for _ in range(e.loop_count):
                    expanded_frames.extend(sub_frames)
                    expanded_durations.extend(sub_durations)

            elif is_layer_block_entry(entry):
                e = entry  # type: LayerBlockEntry
                if not e.timelines:
                    continue
                length = len(e.timelines[0])
                dur = e.default_duration_ms
                for i in range(length):
                    layers_i: List[Tuple[Optional[int], int, int]] = []
                    for timeline in e.timelines:
                        if i >= len(timeline):
                            continue
                        slot = timeline[i]
                        if is_frame_slot(slot):
                            s = slot  # type: FrameSlot
                            layers_i.append((s.material_index, s.x, s.y))
                        elif is_group_slot(slot):
                            s = slot  # type: GroupSlot
                            sub_frames, _ = self._expand_composition_group(
                                s.group_id, group_manager, material_manager
                            )
                            if sub_frames:
                                idx = i % len(sub_frames)
                                for m, px, py in sub_frames[idx]:
                                    layers_i.append((m, px + s.x, py + s.y))
                    expanded_frames.append(layers_i)
                    expanded_durations.append(dur)

        return expanded_frames, expanded_durations

    def get_preview_frames_for_group(
        self,
        group_id: int,
        group_manager: "GroupManager",
        material_manager: MaterialManager,
    ) -> List[Tuple[Image.Image, int]]:
        """Return preview frames (image, duration) for the given group only."""
        expanded_frames, expanded_durations = self._expand_composition_group(
            group_id, group_manager, material_manager
        )
        frames: List[Tuple[Image.Image, int]] = []
        for frame_layers, duration in zip(expanded_frames, expanded_durations):
            composed = self._compose_from_expanded_frame(frame_layers, material_manager)
            frames.append((composed, duration))
        return frames

    def build_gif_from_group(
        self,
        group_id: int,
        group_manager: "GroupManager",
        material_manager: MaterialManager,
        output_path: str,
    ):
        """Export a GIF from the given group only."""
        group = group_manager.get_group(group_id)
        if group is None:
            raise ValueError("Group not found")
        if len(material_manager) == 0:
            raise ValueError("Material list is empty, cannot generate GIF")

        expanded_frames, expanded_durations = self._expand_composition_group(
            group_id, group_manager, material_manager
        )
        if not expanded_frames:
            raise ValueError("No frames to export after expanding group")

        frames: List[Image.Image] = []
        durations: List[int] = []
        for frame_layers, duration in zip(expanded_frames, expanded_durations):
            composed = self._compose_from_expanded_frame(frame_layers, material_manager)
            frames.append(self._convert_frame_for_gif(composed))
            durations.append(duration)

        self.save_gif(frames, durations, output_path)