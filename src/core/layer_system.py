"""
Layer system for multi-layer GIF composition
Supports position, crop, and scale adjustments for each layer
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from PIL import Image
from .utils import ensure_rgba


@dataclass
class Layer:
    """
    Represents a single layer in a frame
    
    Attributes:
        material_index: Index to material in MaterialManager
        x: X position (offset from left)
        y: Y position (offset from top)
        crop_x: Crop region X offset
        crop_y: Crop region Y offset
        crop_width: Crop region width (None = use full width)
        crop_height: Crop region height (None = use full height)
        scale: Scale factor (1.0 = original size)
        opacity: Opacity (0.0-1.0)
        visible: Whether layer is visible
        name: Layer name for identification
    """
    material_index: int
    x: int = 0
    y: int = 0
    crop_x: int = 0
    crop_y: int = 0
    crop_width: Optional[int] = None
    crop_height: Optional[int] = None
    scale: float = 1.0
    opacity: float = 1.0
    visible: bool = True
    name: str = ""
    
    def __post_init__(self):
        if not self.name:
            self.name = f"Layer {self.material_index}"
    
    def copy(self) -> 'Layer':
        """Create a deep copy of this layer"""
        return Layer(
            material_index=self.material_index,
            x=self.x,
            y=self.y,
            crop_x=self.crop_x,
            crop_y=self.crop_y,
            crop_width=self.crop_width,
            crop_height=self.crop_height,
            scale=self.scale,
            opacity=self.opacity,
            visible=self.visible,
            name=self.name
        )
    
    def apply_to_image(self, image: Image.Image) -> Image.Image:
        """
        Apply layer transformations to an image
        Returns the processed image
        """
        img = ensure_rgba(image.copy())
        
        # Apply crop
        if self.crop_width is not None and self.crop_height is not None:
            img_width, img_height = img.size
            
            # Ensure crop region is within bounds
            crop_x = max(0, min(self.crop_x, img_width - 1))
            crop_y = max(0, min(self.crop_y, img_height - 1))
            crop_right = min(crop_x + self.crop_width, img_width)
            crop_bottom = min(crop_y + self.crop_height, img_height)
            
            if crop_right > crop_x and crop_bottom > crop_y:
                img = img.crop((crop_x, crop_y, crop_right, crop_bottom))
        
        # Apply scale
        if abs(self.scale - 1.0) > 0.001 and self.scale > 0:
            new_width = int(img.width * self.scale)
            new_height = int(img.height * self.scale)
            if new_width > 0 and new_height > 0:
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Apply opacity
        if self.opacity < 1.0:
            # Create a copy and adjust alpha channel
            alpha = img.split()[3]
            alpha = alpha.point(lambda p: int(p * self.opacity))
            img.putalpha(alpha)
        
        return img


@dataclass
class LayeredFrame:
    """
    A frame that can contain multiple layers
    
    Attributes:
        layers: List of layers in this frame (bottom to top order)
        duration: Frame duration in milliseconds
        name: Frame name for identification
    """
    layers: List[Layer] = field(default_factory=list)
    duration: int = 100
    name: str = ""
    
    def __post_init__(self):
        if not self.name:
            self.name = "Frame"
    
    def add_layer(self, layer: Layer):
        """Add a layer to the top"""
        self.layers.append(layer)
    
    def insert_layer(self, index: int, layer: Layer):
        """Insert a layer at specific position"""
        self.layers.insert(index, layer)
    
    def remove_layer(self, index: int):
        """Remove a layer by index"""
        if 0 <= index < len(self.layers):
            del self.layers[index]
    
    def move_layer(self, from_index: int, to_index: int):
        """Move a layer from one position to another"""
        if 0 <= from_index < len(self.layers) and 0 <= to_index < len(self.layers):
            layer = self.layers.pop(from_index)
            self.layers.insert(to_index, layer)
    
    def get_layer(self, index: int) -> Optional[Layer]:
        """Get layer by index"""
        if 0 <= index < len(self.layers):
            return self.layers[index]
        return None
    
    def copy(self) -> 'LayeredFrame':
        """Create a deep copy of this frame"""
        return LayeredFrame(
            layers=[layer.copy() for layer in self.layers],
            duration=self.duration,
            name=self.name
        )
    
    def __len__(self):
        return len(self.layers)
    
    def __repr__(self):
        return f"LayeredFrame(layers={len(self.layers)}, duration={self.duration}ms)"


class LayerCompositor:
    """Handles compositing multiple layers into a single image"""
    
    @staticmethod
    def composite_frame(
        layered_frame: LayeredFrame,
        material_manager,
        canvas_size: Tuple[int, int],
        background_color: Tuple[int, int, int, int] = (0, 0, 0, 0)
    ) -> Image.Image:
        """
        Composite all layers in a frame into a single image
        
        Args:
            layered_frame: The frame to composite
            material_manager: MaterialManager to get source images
            canvas_size: Output canvas size (width, height)
            background_color: Background color (R, G, B, A)
        
        Returns:
            Composited image
        """
        # Create canvas
        canvas = Image.new('RGBA', canvas_size, background_color)
        
        # Composite each layer from bottom to top
        for layer in layered_frame.layers:
            if not layer.visible:
                continue
            
            # Get material image
            material = material_manager.get_material(layer.material_index)
            if material is None:
                continue
            
            material_img, _ = material
            
            # Apply layer transformations
            processed_img = layer.apply_to_image(material_img)
            
            # Paste onto canvas at specified position
            try:
                canvas.paste(processed_img, (layer.x, layer.y), processed_img)
            except Exception as e:
                # If paste fails (e.g., out of bounds), skip this layer
                print(f"Warning: Failed to paste layer {layer.name}: {e}")
                continue
        
        return canvas

