from typing import Tuple
from PIL import Image


def ensure_rgba(image: Image.Image) -> Image.Image:
    if image.mode != 'RGBA':
        return image.convert('RGBA')
    return image


def resize_image(image: Image.Image, size: Tuple[int, int], keep_aspect: bool = True) -> Image.Image:
    if keep_aspect:
        image.thumbnail(size, Image.Resampling.LANCZOS)
        return image
    else:
        return image.resize(size, Image.Resampling.LANCZOS)


def create_background(size: Tuple[int, int], color: Tuple[int, int, int, int] = (255, 255, 255, 255)) -> Image.Image:
    return Image.new('RGBA', size, color)


def paste_center(background: Image.Image, foreground: Image.Image) -> Image.Image:
    bg_w, bg_h = background.size
    fg_w, fg_h = foreground.size
    
    x = (bg_w - fg_w) // 2
    y = (bg_h - fg_h) // 2
    
    result = background.copy()
    result.paste(foreground, (x, y), foreground if foreground.mode == 'RGBA' else None)
    
    return result


def validate_image_file(filepath: str) -> bool:
    try:
        with Image.open(filepath) as img:
            img.verify()
        return True
    except Exception:
        return False

