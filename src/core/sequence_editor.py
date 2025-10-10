from typing import List, Tuple
from PIL import Image
from copy import deepcopy


class Frame:
    
    def __init__(self, material_index: int, duration: int = 100):
        self.material_index = material_index
        self.duration = duration
    
    def __repr__(self):
        return f"Frame(material={self.material_index}, duration={self.duration}ms)"


class SequenceEditor:
    
    def __init__(self):
        self.frames: List[Frame] = []
        self.default_duration: int = 100
    
    def add_frame(self, material_index: int, duration: int = None):
        if duration is None:
            duration = self.default_duration
        
        frame = Frame(material_index, duration)
        self.frames.append(frame)
    
    def insert_frame(self, position: int, material_index: int, duration: int = None):
        if duration is None:
            duration = self.default_duration
        
        frame = Frame(material_index, duration)
        self.frames.insert(position, frame)
    
    def remove_frame(self, position: int):
        if 0 <= position < len(self.frames):
            del self.frames[position]
    
    def move_frame(self, from_pos: int, to_pos: int):
        if 0 <= from_pos < len(self.frames) and 0 <= to_pos < len(self.frames):
            frame = self.frames.pop(from_pos)
            self.frames.insert(to_pos, frame)
    
    def duplicate_frame(self, position: int):
        if 0 <= position < len(self.frames):
            frame = self.frames[position]
            new_frame = Frame(frame.material_index, frame.duration)
            self.frames.insert(position + 1, new_frame)
    
    def set_frame_duration(self, position: int, duration: int):
        if 0 <= position < len(self.frames):
            self.frames[position].duration = duration
    
    def set_all_durations(self, duration: int):
        for frame in self.frames:
            frame.duration = duration
    
    def set_sequence_from_pattern(self, pattern: List[int], duration: int = None):
        if duration is None:
            duration = self.default_duration
        
        self.frames.clear()
        for material_idx in pattern:
            self.add_frame(material_idx, duration)
    
    def repeat_sequence(self, times: int):
        if not self.frames:
            return
        
        original_frames = self.frames.copy()
        for _ in range(times - 1):
            for frame in original_frames:
                self.add_frame(frame.material_index, frame.duration)
    
    def reverse_sequence(self):
        self.frames.reverse()
    
    def get_frame_count(self) -> int:
        return len(self.frames)
    
    def get_total_duration(self) -> int:
        return sum(frame.duration for frame in self.frames)
    
    def get_frames(self) -> List[Frame]:
        return self.frames.copy()
    
    def clear(self):
        self.frames.clear()
    
    def export_pattern(self) -> List[int]:
        return [frame.material_index for frame in self.frames]
    
    def export_durations(self) -> List[int]:
        return [frame.duration for frame in self.frames]
    
    def __len__(self):
        return len(self.frames)
    
    def __getitem__(self, index):
        return self.frames[index]
    
    def __repr__(self):
        return f"SequenceEditor(frames={len(self.frames)}, duration={self.get_total_duration()}ms)"

