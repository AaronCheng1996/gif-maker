from typing import List, Tuple
from pathlib import Path
from PIL import Image, ImageSequence
from .utils import ensure_rgba


class ImageLoader:
    
    @staticmethod
    def load_image(filepath: str) -> Image.Image:
        img = Image.open(filepath)
        return ensure_rgba(img)
    
    @staticmethod
    def load_gif_frames(filepath: str) -> List[Tuple[Image.Image, int]]:
        frames = []
        with Image.open(filepath) as img:
            if not getattr(img, 'is_animated', False):
                duration = img.info.get('duration', 100)
                frames.append((ensure_rgba(img.copy()), duration))
            else:
                for frame in ImageSequence.Iterator(img):
                    duration = frame.info.get('duration', 100)
                    frames.append((ensure_rgba(frame.copy()), duration))
        
        return frames
    
    @staticmethod
    def split_into_tiles(image: Image.Image, rows: int, cols: int) -> List[Image.Image]:
        img_width, img_height = image.size
        tile_width = img_width // cols
        tile_height = img_height // rows
        
        tiles = []
        for row in range(rows):
            for col in range(cols):
                left = col * tile_width
                upper = row * tile_height
                right = left + tile_width
                lower = upper + tile_height
                
                tile = image.crop((left, upper, right, lower))
                tiles.append(tile)
        
        return tiles
    
    @staticmethod
    def split_by_tile_size(image: Image.Image, tile_width: int, tile_height: int) -> List[Image.Image]:
        img_width, img_height = image.size
        cols = img_width // tile_width
        rows = img_height // tile_height
        
        tiles = []
        for row in range(rows):
            for col in range(cols):
                left = col * tile_width
                upper = row * tile_height
                right = left + tile_width
                lower = upper + tile_height
                
                tile = image.crop((left, upper, right, lower))
                tiles.append(tile)
        
        return tiles


class MaterialManager:
    
    def __init__(self):
        self.materials: List[Tuple[Image.Image, str]] = []
        self.durations: List[int] = []
    
    def add_material(self, image: Image.Image, name: str = "", duration: int = 100):
        if not name:
            name = f"Material_{len(self.materials) + 1}"
        
        self.materials.append((ensure_rgba(image), name))
        self.durations.append(duration)
    
    def add_materials_from_list(self, images: List[Image.Image], name_prefix: str = "Material", duration: int = 100):
        for i, img in enumerate(images):
            name = f"{name_prefix}_{i + 1}"
            self.add_material(img, name, duration)
    
    def load_from_image(self, filepath: str, name: str = ""):
        img = ImageLoader.load_image(filepath)
        if not name:
            name = Path(filepath).stem
        self.add_material(img, name)
    
    def load_from_gif(self, filepath: str, name_prefix: str = ""):
        frames = ImageLoader.load_gif_frames(filepath)
        if not name_prefix:
            name_prefix = Path(filepath).stem
        
        for i, (frame, duration) in enumerate(frames):
            name = f"{name_prefix}_frame_{i + 1}"
            self.add_material(frame, name, duration)
    
    def load_from_tiles(self, filepath: str, rows: int, cols: int, name_prefix: str = ""):
        img = ImageLoader.load_image(filepath)
        tiles = ImageLoader.split_into_tiles(img, rows, cols)
        
        if not name_prefix:
            name_prefix = Path(filepath).stem
        
        self.add_materials_from_list(tiles, f"{name_prefix}_tile")
    
    def get_material(self, index: int) -> Tuple[Image.Image, str]:
        if 0 <= index < len(self.materials):
            return self.materials[index]
        return None
    
    def get_all_materials(self) -> List[Tuple[Image.Image, str]]:
        return self.materials.copy()
    
    def remove_material(self, index: int):
        if 0 <= index < len(self.materials):
            del self.materials[index]
            del self.durations[index]
    
    def clear(self):
        self.materials.clear()
        self.durations.clear()
    
    def __len__(self):
        return len(self.materials)

