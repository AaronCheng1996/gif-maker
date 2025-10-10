from typing import List, Tuple, Optional
from pathlib import Path
from PIL import Image
from .utils import create_background, paste_center, ensure_rgba
from .sequence_editor import SequenceEditor, Frame
from .image_loader import MaterialManager


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
            
            if frame_img.mode == 'RGBA':
                if self.background_color[3] == 0:
                    frame_img = frame_img.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
                    frame_img.info['transparency'] = 255
                else:
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
            
            if frame_img.mode == 'RGBA':
                if self.background_color[3] == 0:
                    frame_img = frame_img.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
                    frame_img.info['transparency'] = 255
                else:
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
            save_kwargs['transparency'] = 255
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

