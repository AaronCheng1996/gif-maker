from typing import List, Tuple, Optional
from pathlib import Path
from PIL import Image
from .utils import create_background, paste_center, ensure_rgba
from .sequence_editor import SequenceEditor, Frame
from .image_loader import MaterialManager
from .layer_system import LayeredFrame, LayerCompositor


class GifBuilder:
    
    def __init__(self):
        self.output_size: Optional[Tuple[int, int]] = None
        self.background_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
        self.loop: int = 0
        self.optimize: bool = True
        self.disposal: int = 2
    
    def set_output_size(self, width: int, height: int):
        self.output_size = (width, height)
    
    def set_background_color(self, r: int, g: int, b: int, a: int = 255):
        self.background_color = (r, g, b, a)
    
    def set_loop(self, loop: int):
        self.loop = loop
    
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
                    # For transparent background, convert to P mode with transparency
                    # method: 0=MEDIANCUT, 2=FASTOCTREE, 3=LIBIMAGEQUANT
                    frame_img = frame_img.quantize(colors=255, method=2)
                    # Find the transparent color index (usually 0 for transparent pixels)
                    if 'transparency' not in frame_img.info:
                        # Set the first palette entry (index 0) as transparent
                        frame_img.info['transparency'] = 0
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
                    # For transparent background, convert to P mode with transparency
                    # method: 0=MEDIANCUT, 2=FASTOCTREE, 3=LIBIMAGEQUANT
                    frame_img = frame_img.quantize(colors=255, method=2)
                    # Find the transparent color index (usually 0 for transparent pixels)
                    if 'transparency' not in frame_img.info:
                        # Set the first palette entry (index 0) as transparent
                        frame_img.info['transparency'] = 0
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
                    # For transparent background, convert to P mode with transparency
                    composited = composited.quantize(colors=255, method=2)
                    if 'transparency' not in composited.info:
                        composited.info['transparency'] = 0
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