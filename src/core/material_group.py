"""
Material Group - Represents an animation clip composed of multiple materials

A MaterialGroup is a reusable animation sequence that can be expanded into frames.
Example: A walk cycle with frames [1,2,3,4] played at 100ms per frame, looped 3 times.
"""

from typing import List, Tuple
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
    
    def copy(self) -> 'MaterialGroup':
        """
        Create a deep copy of this group
        
        Returns:
            New MaterialGroup instance
        """
        return MaterialGroup(
            material_indices=self.material_indices.copy(),
            frame_duration=self.frame_duration,
            loop_count=self.loop_count,
            name=self.name
        )
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization
        
        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "material_indices": list(self.material_indices),
            "frame_duration": self.frame_duration,
            "loop_count": self.loop_count
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'MaterialGroup':
        """
        Create MaterialGroup from dictionary
        
        Args:
            data: Dictionary with group data
        
        Returns:
            MaterialGroup instance
        """
        return MaterialGroup(
            material_indices=list(data.get("material_indices", [])),
            frame_duration=int(data.get("frame_duration", 100)),
            loop_count=int(data.get("loop_count", 1)),
            name=str(data.get("name", ""))
        )
    
    def __repr__(self):
        return (f"MaterialGroup(name='{self.name}', "
                f"materials={len(self.material_indices)}, "
                f"loops={self.loop_count}, "
                f"total_frames={self.get_total_frames()})")

