"""
Template Manager - Export and import timeline templates
Allows saving and reusing timeline structures with different materials
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from .layer_system import Layer, LayeredFrame
from .layered_sequence_editor import LayeredSequenceEditor


class TemplateManager:
    """
    Manages template export/import for timeline structures
    
    Templates store the structure of frames and layers, with material references
    replaced by relative indices. This allows applying the same timeline structure
    to different sets of materials.
    """
    
    VERSION = "1.0"
    
    @staticmethod
    def export_template(
        layered_sequence_editor: LayeredSequenceEditor,
        output_width: int,
        output_height: int,
        loop_count: int,
        transparent_bg: bool,
        material_count: int,
        color_count: int = 256
    ) -> Dict[str, Any]:
        """
        Export current timeline as a template
        
        Args:
            layered_sequence_editor: The sequence editor with frames
            output_width: Output GIF width
            output_height: Output GIF height
            loop_count: GIF loop count
            transparent_bg: Whether background is transparent
            material_count: Total number of materials used
            color_count: Number of colors in the palette (256, 128, 64, 32, 16)
        
        Returns:
            Template dictionary
        """
        template = {
            "version": TemplateManager.VERSION,
            "settings": {
                "output_width": output_width,
                "output_height": output_height,
                "loop_count": loop_count,
                "transparent_bg": transparent_bg,
                "material_count": material_count,
                "color_count": color_count
            },
            "frames": []
        }
        
        # Export each frame
        for frame_idx, frame in enumerate(layered_sequence_editor.get_frames()):
            frame_data = {
                "index": frame_idx,
                "duration": frame.duration,
                "name": frame.name,
                "layers": []
            }
            
            # Export each layer
            for layer_idx, layer in enumerate(frame.layers):
                layer_data = {
                    "index": layer_idx,
                    "material_index": layer.material_index,  # Relative material index
                    "name": layer.name,
                    "x": layer.x,
                    "y": layer.y,
                    "crop_x": layer.crop_x,
                    "crop_y": layer.crop_y,
                    "crop_width": layer.crop_width,
                    "crop_height": layer.crop_height,
                    "scale": layer.scale,
                    "opacity": layer.opacity,
                    "visible": layer.visible
                }
                frame_data["layers"].append(layer_data)
            
            template["frames"].append(frame_data)
        
        return template
    
    @staticmethod
    def save_template_to_file(template: Dict[str, Any], file_path: str):
        """
        Save template to JSON file
        
        Args:
            template: Template dictionary
            file_path: Output file path
        """
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def load_template_from_file(file_path: str) -> Dict[str, Any]:
        """
        Load template from JSON file
        
        Args:
            file_path: Template file path
        
        Returns:
            Template dictionary
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            template = json.load(f)
        
        # Validate version
        if "version" not in template:
            raise ValueError("Invalid template: missing version")
        
        if template["version"] != TemplateManager.VERSION:
            # In future, handle version migration here
            pass
        
        return template
    
    @staticmethod
    def apply_template(
        template: Dict[str, Any],
        material_index_mapping: Optional[Dict[int, int]] = None
    ) -> Tuple[LayeredSequenceEditor, Dict[str, Any]]:
        """
        Apply template to create a new sequence
        
        Args:
            template: Template dictionary
            material_index_mapping: Mapping from template material indices to new material indices
                                   If None, uses identity mapping (same indices)
        
        Returns:
            Tuple of (LayeredSequenceEditor, settings dictionary)
        """
        # Create new sequence editor
        editor = LayeredSequenceEditor()
        
        # Default to identity mapping if not provided
        if material_index_mapping is None:
            material_index_mapping = {}
        
        # Reconstruct frames
        for frame_data in template["frames"]:
            frame = LayeredFrame(
                duration=frame_data["duration"],
                name=frame_data.get("name", f"Frame {frame_data['index'] + 1}")
            )
            
            # Reconstruct layers
            for layer_data in frame_data["layers"]:
                # Map material index
                old_material_idx = layer_data["material_index"]
                new_material_idx = material_index_mapping.get(old_material_idx, old_material_idx)
                
                layer = Layer(
                    material_index=new_material_idx,
                    name=layer_data.get("name", f"Layer {layer_data['index'] + 1}"),
                    x=layer_data.get("x", 0),
                    y=layer_data.get("y", 0),
                    crop_x=layer_data.get("crop_x", 0),
                    crop_y=layer_data.get("crop_y", 0),
                    crop_width=layer_data.get("crop_width"),
                    crop_height=layer_data.get("crop_height"),
                    scale=layer_data.get("scale", 1.0),
                    opacity=layer_data.get("opacity", 1.0),
                    visible=layer_data.get("visible", True)
                )
                frame.add_layer(layer)
            
            editor.add_frame(frame)
        
        # Extract settings
        settings = template.get("settings", {})
        
        return editor, settings
    
    @staticmethod
    def get_template_info(template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get summary information about a template
        
        Args:
            template: Template dictionary
        
        Returns:
            Info dictionary
        """
        settings = template.get("settings", {})
        frames = template.get("frames", [])
        
        # Collect material indices used
        material_indices = set()
        total_layers = 0
        
        for frame in frames:
            for layer in frame.get("layers", []):
                material_indices.add(layer["material_index"])
                total_layers += 1
        
        total_duration = sum(frame.get("duration", 100) for frame in frames)
        
        return {
            "version": template.get("version", "unknown"),
            "frame_count": len(frames),
            "material_count": settings.get("material_count", len(material_indices)),
            "unique_materials_used": len(material_indices),
            "total_layers": total_layers,
            "total_duration_ms": total_duration,
            "output_size": (settings.get("output_width", 0), settings.get("output_height", 0)),
            "loop_count": settings.get("loop_count", 0),
            "transparent_bg": settings.get("transparent_bg", False)
        }

