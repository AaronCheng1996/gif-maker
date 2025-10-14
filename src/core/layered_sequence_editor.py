"""
Layered Sequence Editor - Manages a sequence of layered frames
"""

from typing import List, Optional
from .layer_system import LayeredFrame, Layer


class LayeredSequenceEditor:
    """
    Manages a sequence of layered frames for GIF animation
    """
    
    def __init__(self):
        self.frames: List[LayeredFrame] = []
        self.default_duration: int = 100
    
    def add_frame(self, layered_frame: LayeredFrame):
        """Add a layered frame to the sequence"""
        self.frames.append(layered_frame)
    
    def insert_frame(self, position: int, layered_frame: LayeredFrame):
        """Insert a layered frame at specific position"""
        self.frames.insert(position, layered_frame)
    
    def remove_frame(self, position: int):
        """Remove a frame by position"""
        if 0 <= position < len(self.frames):
            del self.frames[position]
    
    def move_frame(self, from_pos: int, to_pos: int):
        """Move a frame from one position to another"""
        if 0 <= from_pos < len(self.frames) and 0 <= to_pos < len(self.frames):
            frame = self.frames.pop(from_pos)
            self.frames.insert(to_pos, frame)
    
    def duplicate_frame(self, position: int):
        """Duplicate a frame"""
        if 0 <= position < len(self.frames):
            frame = self.frames[position].copy()
            self.frames.insert(position + 1, frame)
    
    def get_frame(self, position: int) -> Optional[LayeredFrame]:
        """Get a frame by position"""
        if 0 <= position < len(self.frames):
            return self.frames[position]
        return None
    
    def get_frames(self) -> List[LayeredFrame]:
        """Get all frames"""
        return self.frames.copy()
    
    def clear(self):
        """Clear all frames"""
        self.frames.clear()
    
    def __len__(self):
        return len(self.frames)
    
    def __getitem__(self, index):
        return self.frames[index]
    
    def __repr__(self):
        total_duration = sum(frame.duration for frame in self.frames)
        return f"LayeredSequenceEditor(frames={len(self.frames)}, duration={total_duration}ms)"
    
    @staticmethod
    def from_simple_sequence(material_indices: List[int], duration: int = 100) -> 'LayeredSequenceEditor':
        """
        Create a layered sequence from simple material indices (for backward compatibility)
        Each frame will have a single layer
        """
        editor = LayeredSequenceEditor()
        
        for material_idx in material_indices:
            frame = LayeredFrame(duration=duration)
            layer = Layer(material_index=material_idx, name=f"Material {material_idx}")
            frame.add_layer(layer)
            editor.add_frame(frame)
        
        return editor

