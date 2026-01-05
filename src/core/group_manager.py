"""
Group Manager - Manages a collection of MaterialGroups

The GroupManager maintains a list of MaterialGroups that can be used in the animation.
Groups can be referenced by index, similar to how materials are managed.
"""

from typing import List, Optional
from .material_group import MaterialGroup


class GroupManager:
    """
    Manages a collection of MaterialGroups
    
    Groups are stored in a list and can be accessed by index.
    This mirrors the MaterialManager design for consistency.
    """
    
    def __init__(self):
        self.groups: List[MaterialGroup] = []
    
    def add_group(self, group: MaterialGroup) -> int:
        """
        Add a group to the manager
        
        Args:
            group: MaterialGroup to add
        
        Returns:
            Index of the added group
        """
        self.groups.append(group)
        return len(self.groups) - 1
    
    def create_group_from_materials(
        self,
        material_indices: List[int],
        frame_duration: int = 100,
        loop_count: int = 1,
        name: str = ""
    ) -> int:
        """
        Create and add a new group from material indices
        
        Args:
            material_indices: List of material indices
            frame_duration: Duration for each frame in ms
            loop_count: Number of times to loop
            name: Display name for the group
        
        Returns:
            Index of the created group
        """
        group = MaterialGroup(
            material_indices=material_indices,
            frame_duration=frame_duration,
            loop_count=loop_count,
            name=name
        )
        return self.add_group(group)
    
    def get_group(self, index: int) -> Optional[MaterialGroup]:
        """
        Get a group by index
        
        Args:
            index: Group index
        
        Returns:
            MaterialGroup or None if index is invalid
        """
        if 0 <= index < len(self.groups):
            return self.groups[index]
        return None
    
    def remove_group(self, index: int):
        """
        Remove a group by index
        
        Args:
            index: Group index to remove
        """
        if 0 <= index < len(self.groups):
            del self.groups[index]
    
    def get_all_groups(self) -> List[MaterialGroup]:
        """
        Get all groups
        
        Returns:
            Copy of the groups list
        """
        return self.groups.copy()
    
    def clear(self):
        """Clear all groups"""
        self.groups.clear()
    
    def update_group(self, index: int, group: MaterialGroup):
        """
        Update a group at specific index
        
        Args:
            index: Group index
            group: New MaterialGroup to replace
        """
        if 0 <= index < len(self.groups):
            self.groups[index] = group
    
    def move_group(self, from_index: int, to_index: int):
        """
        Move a group from one position to another
        
        Args:
            from_index: Source index
            to_index: Destination index
        """
        if 0 <= from_index < len(self.groups) and 0 <= to_index < len(self.groups):
            group = self.groups.pop(from_index)
            self.groups.insert(to_index, group)
    
    def __len__(self):
        return len(self.groups)
    
    def __getitem__(self, index: int) -> MaterialGroup:
        return self.groups[index]
    
    def __repr__(self):
        return f"GroupManager(groups={len(self.groups)})"

