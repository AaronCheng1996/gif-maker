"""
Template Manager - Export and import timeline templates
Allows saving and reusing timeline structures with different materials
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from .layer_system import Layer, LayeredFrame
from .layered_sequence_editor import LayeredSequenceEditor
from .multi_timeline import MultiTimelineEditor, Timeline, TimelineFrame


class TemplateManager:
    """
    Manages template export/import for timeline structures
    
    Templates store the structure of frames and layers, with material references
    replaced by relative indices. This allows applying the same timeline structure
    to different sets of materials.
    """
    
    VERSION = "2.0"
    
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

    # ----- Multi-timeline templates -----
    @staticmethod
    def export_multi_template(
        multi_editor: MultiTimelineEditor,
        output_width: int,
        output_height: int,
        loop_count: int,
        transparent_bg: bool,
        color_count: int = 256
    ) -> Dict[str, Any]:
        """
        Export the multi-timeline editor state as a template.

        The template schema:
        {
          "version": "2.0",
          "format": "multi_timeline",
          "settings": { ... },
          "timebase": { "durations_ms": [int, ...] },
          "main_timeline_index": int,
          "timelines": [
             { "name": str, "offset_x": int, "offset_y": int,
               "frames": [ null | {"material_index": int, "x": int, "y": int}, ... ]
             }, ...
          ]
        }
        """
        template: Dict[str, Any] = {
            "version": TemplateManager.VERSION,
            "format": "multi_timeline",
            "settings": {
                "output_width": output_width,
                "output_height": output_height,
                "loop_count": loop_count,
                "transparent_bg": transparent_bg,
                "color_count": color_count,
            },
            "timebase": {
                "durations_ms": list(multi_editor.durations_ms),
            },
            "main_timeline_index": int(multi_editor.main_timeline_index),
            "timelines": []
        }

        frame_count = len(multi_editor.durations_ms)
        for tl in multi_editor.timelines:
            tl_entry: Dict[str, Any] = {
                "name": tl.name,
                "offset_x": tl.offset_x,
                "offset_y": tl.offset_y,
                "frames": []
            }
            for i in range(frame_count):
                if i < len(tl.frames):
                    fr = tl.frames[i]
                    if fr.material_index is None:
                        tl_entry["frames"].append(None)
                    else:
                        tl_entry["frames"].append({
                            "material_index": fr.material_index,
                            "x": fr.x,
                            "y": fr.y,
                        })
                else:
                    tl_entry["frames"].append(None)
            template["timelines"].append(tl_entry)

        return template

    @staticmethod
    def apply_multi_template(
        template: Dict[str, Any],
        material_index_mapping: Optional[Dict[int, int]] = None
    ) -> Tuple[MultiTimelineEditor, Dict[str, Any]]:
        """
        Apply a multi-timeline template to create a new MultiTimelineEditor

        Args:
            template: Multi-timeline template dictionary
            material_index_mapping: Optional mapping from template material indices to
                                    current material indices. Defaults to identity.
        Returns:
            (MultiTimelineEditor, settings)
        """
        editor = MultiTimelineEditor()

        # Default to identity mapping
        if material_index_mapping is None:
            material_index_mapping = {}

        # Load timebase
        timebase = template.get("timebase", {})
        durations = list(timebase.get("durations_ms", []))
        editor.durations_ms = durations

        # Load timelines
        timelines_data: List[Dict[str, Any]] = template.get("timelines", [])
        frame_count = len(durations)
        for tl_data in timelines_data:
            name = tl_data.get("name", f"Timeline {len(editor.timelines) + 1}")
            tl_index = editor.add_timeline(name)
            tl = editor.get_timeline(tl_index)
            if tl is None:
                continue
            tl.offset_x = int(tl_data.get("offset_x", 0))
            tl.offset_y = int(tl_data.get("offset_y", 0))

            frames_data = tl_data.get("frames", [])
            # Ensure length
            while len(tl.frames) < frame_count:
                tl.frames.append(TimelineFrame())
            for i in range(min(frame_count, len(frames_data))):
                fr = frames_data[i]
                if fr is None:
                    tl.frames[i] = TimelineFrame()
                else:
                    # Map material index if given
                    old_idx = fr.get("material_index")
                    new_idx = material_index_mapping.get(old_idx, old_idx) if old_idx is not None else None
                    tl.frames[i] = TimelineFrame(
                        material_index=new_idx,
                        x=int(fr.get("x", 0)),
                        y=int(fr.get("y", 0)),
                    )

        # Main timeline index
        main_idx = int(template.get("main_timeline_index", 0))
        editor.set_main_timeline(min(max(0, main_idx), len(editor.timelines) - 1))

        settings = template.get("settings", {})
        return editor, settings

    @staticmethod
    def get_template_info(template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get summary information about a template. Supports both legacy layered and
        new multi-timeline formats.
        """
        # Multi-timeline format detection
        if template.get("format") == "multi_timeline" or ("timelines" in template and "timebase" in template):
            settings = template.get("settings", {})
            durations = template.get("timebase", {}).get("durations_ms", [])
            timelines = template.get("timelines", [])
            frame_count = len(durations)
            unique_materials = set()
            placements = 0
            for tl in timelines:
                for fr in tl.get("frames", []):
                    if isinstance(fr, dict):
                        mi = fr.get("material_index")
                        if mi is not None:
                            unique_materials.add(mi)
                            placements += 1
            total_duration = sum(int(d) for d in durations)
            return {
                "version": template.get("version", "unknown"),
                "format": "multi_timeline",
                "frame_count": frame_count,
                "timeline_count": len(timelines),
                "unique_materials_used": len(unique_materials),
                "placements": placements,
                "timebase_total_duration_ms": total_duration,
                "output_size": (settings.get("output_width", 0), settings.get("output_height", 0)),
                "loop_count": settings.get("loop_count", 0),
                "transparent_bg": settings.get("transparent_bg", False),
                "color_count": settings.get("color_count", 256),
            }

        # Fallback to legacy layered format
        settings = template.get("settings", {})
        frames = template.get("frames", [])
        material_indices = set()
        total_layers = 0
        for frame in frames:
            for layer in frame.get("layers", []):
                material_indices.add(layer["material_index"])
                total_layers += 1
        total_duration = sum(frame.get("duration", 100) for frame in frames)
        return {
            "version": template.get("version", "unknown"),
            "format": "layered",
            "frame_count": len(frames),
            "material_count": settings.get("material_count", len(material_indices)),
            "unique_materials_used": len(material_indices),
            "total_layers": total_layers,
            "total_duration_ms": total_duration,
            "output_size": (settings.get("output_width", 0), settings.get("output_height", 0)),
            "loop_count": settings.get("loop_count", 0),
            "transparent_bg": settings.get("transparent_bg", False)
        }
    
    

