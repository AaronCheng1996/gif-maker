"""
Material Group - Represents an animation clip composed of multiple materials

A MaterialGroup is a reusable animation sequence that can be expanded into frames.
Example: A walk cycle with frames [1,2,3,4] played at 100ms per frame, looped 3 times.
"""

from typing import List, Tuple, Dict
from dataclasses import dataclass, field


@dataclass
class MaterialGroup:
    """
    Represents a group of materials that form an animation clip
    
    Attributes:
        material_indices: List of material indices in sequence
        frame_duration: Duration for each frame in milliseconds
        loop_count: Number of times to loop the sequence
        name: Display name for the group
    
    Example:
        group = MaterialGroup(
            material_indices=[1, 2, 3, 4],
            frame_duration=100,
            loop_count=3,
            name="Walk Cycle"
        )
        # This expands to 12 frames: [1,2,3,4, 1,2,3,4, 1,2,3,4]
    """
    material_indices: List[int] = field(default_factory=list)
    frame_duration: int = 100
    loop_count: int = 1
    name: str = ""
    independent_offsets: bool = False  # If True, each material can have independent offset when aligned
    material_offsets: Dict[int, Tuple[int, int]] = field(default_factory=dict)  # Per-material offsets for independent mode
    # Key: index in material_indices (0, 1, 2...)
    # Value: (offset_x, offset_y) relative to group position
    
    def __post_init__(self):
        if not self.name:
            self.name = f"Group_{len(self.material_indices)}"
    
    def expand_to_frames(self) -> List[Tuple[int, int]]:
        """
        Expand the group into a list of (material_index, duration) tuples
        
        Returns:
            List of (material_index, duration) tuples representing all frames
        """
        expanded = []
        for _ in range(self.loop_count):
            for material_idx in self.material_indices:
                expanded.append((material_idx, self.frame_duration))
        return expanded
    
    def get_total_frames(self) -> int:
        """
        Get the total number of frames after expansion
        
        Returns:
            Total frame count
        """
        return len(self.material_indices) * self.loop_count
    
    def get_total_duration(self) -> int:
        """
        Get the total duration in milliseconds after expansion
        
        Returns:
            Total duration in ms
        """
        return self.get_total_frames() * self.frame_duration
    
    def get_frame_at_index(self, frame_index: int) -> Tuple[int, int]:
        """
        Get the frame (material_index, duration) at a specific expanded index
        
        Args:
            frame_index: Index in the expanded sequence
        
        Returns:
            (material_index, duration) tuple
        
        Raises:
            IndexError: If frame_index is out of range
        """
        total_frames = self.get_total_frames()
        if not 0 <= frame_index < total_frames:
            raise IndexError(f"Frame index {frame_index} out of range [0, {total_frames})")
        
        material_idx = self.material_indices[frame_index % len(self.material_indices)]
        return (material_idx, self.frame_duration)
    
    def get_material_offset(self, mat_list_idx: int) -> Tuple[int, int]:
        """
        Get offset for a material at specific index in material_indices list
        
        Args:
            mat_list_idx: Index in material_indices list (0, 1, 2...)
        
        Returns:
            (offset_x, offset_y) tuple, defaults to (0, 0) if not set
        """
        return self.material_offsets.get(mat_list_idx, (0, 0))
    
    def set_material_offset(self, mat_list_idx: int, x: int, y: int):
        """
        Set offset for a material at specific index in material_indices list
        Only has effect if independent_offsets is True
        
        Args:
            mat_list_idx: Index in material_indices list (0, 1, 2...)
            x: X offset
            y: Y offset
        """
        if self.independent_offsets:
            self.material_offsets[mat_list_idx] = (x, y)
    
    def clear_material_offsets(self):
        """Clear all individual material offsets"""
        self.material_offsets.clear()
    
    def copy(self) -> 'MaterialGroup':
        """
        Create a deep copy of this group
        
        Returns:
            New MaterialGroup instance
        """
        new_group = MaterialGroup(
            material_indices=self.material_indices.copy(),
            frame_duration=self.frame_duration,
            loop_count=self.loop_count,
            name=self.name,
            independent_offsets=self.independent_offsets
        )
        new_group.material_offsets = self.material_offsets.copy()
        return new_group
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization
        
        Returns:
            Dictionary representation
        """
        result = {
            "name": self.name,
            "material_indices": list(self.material_indices),
            "frame_duration": self.frame_duration,
            "loop_count": self.loop_count,
            "independent_offsets": self.independent_offsets
        }
        # Only save material_offsets if independent_offsets is True and dict is not empty
        if self.independent_offsets and self.material_offsets:
            # Convert int keys to str for JSON compatibility
            result["material_offsets"] = {str(k): list(v) for k, v in self.material_offsets.items()}
        return result
    
    @staticmethod
    def from_dict(data: dict) -> 'MaterialGroup':
        """
        Create MaterialGroup from dictionary
        
        Args:
            data: Dictionary with group data
        
        Returns:
            MaterialGroup instance
        """
        group = MaterialGroup(
            material_indices=list(data.get("material_indices", [])),
            frame_duration=int(data.get("frame_duration", 100)),
            loop_count=int(data.get("loop_count", 1)),
            name=str(data.get("name", "")),
            independent_offsets=bool(data.get("independent_offsets", False))
        )
        # Load material_offsets if present
        if "material_offsets" in data:
            offsets_data = data["material_offsets"]
            # Convert str keys back to int
            group.material_offsets = {int(k): tuple(v) for k, v in offsets_data.items()}
        return group
    
    def __repr__(self):
        return (f"MaterialGroup(name='{self.name}', "
                f"materials={len(self.material_indices)}, "
                f"loops={self.loop_count}, "
                f"total_frames={self.get_total_frames()})")

