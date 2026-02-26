"""
Group Manager - Manages a collection of CompositionGroups

The GroupManager maintains a list of CompositionGroups (group-led nested model).
Groups are stored in a list and accessed by index (used as group_id).
Root group is the top-level composition; current selection for preview/export
is tracked by the application (e.g. main window).
"""

from typing import List, Optional
from .composition_group import CompositionGroup


class GroupManager:
    """
    Manages a collection of CompositionGroups.

    Groups are stored in a list and can be accessed by index (group_id).
    root_group_id points to the document root; UI stores selected group for preview/export.
    """

    def __init__(self):
        self.groups: List[CompositionGroup] = []
        self.root_group_id: Optional[int] = None

    def add_group(self, group: CompositionGroup) -> int:
        """
        Add a group to the manager.

        Args:
            group: CompositionGroup to add

        Returns:
            Index (group_id) of the added group
        """
        self.groups.append(group)
        gid = len(self.groups) - 1
        if self.root_group_id is None:
            self.root_group_id = gid
        return gid

    def get_group(self, index: int) -> Optional[CompositionGroup]:
        """
        Get a group by index (group_id).

        Args:
            index: Group index

        Returns:
            CompositionGroup or None if index is invalid
        """
        if 0 <= index < len(self.groups):
            return self.groups[index]
        return None

    def remove_group(self, index: int):
        """
        Remove a group by index. Does not fix references in other groups.

        Args:
            index: Group index to remove
        """
        if 0 <= index < len(self.groups):
            del self.groups[index]
            if self.root_group_id == index:
                self.root_group_id = 0 if self.groups else None
            elif self.root_group_id is not None and self.root_group_id > index:
                self.root_group_id -= 1

    def get_all_groups(self) -> List[CompositionGroup]:
        """Return a copy of the groups list."""
        return self.groups.copy()

    def clear(self):
        """Clear all groups and reset root."""
        self.groups.clear()
        self.root_group_id = None

    def update_group(self, index: int, group: CompositionGroup):
        """
        Update a group at a specific index.

        Args:
            index: Group index
            group: New CompositionGroup to replace
        """
        if 0 <= index < len(self.groups):
            self.groups[index] = group

    def move_group(self, from_index: int, to_index: int):
        """
        Move a group from one position to another.

        Args:
            from_index: Source index
            to_index: Destination index
        """
        if 0 <= from_index < len(self.groups) and 0 <= to_index < len(self.groups):
            group = self.groups.pop(from_index)
            self.groups.insert(to_index, group)
            if self.root_group_id == from_index:
                self.root_group_id = to_index
            elif self.root_group_id is not None:
                if from_index < self.root_group_id <= to_index:
                    self.root_group_id -= 1
                elif to_index <= self.root_group_id < from_index:
                    self.root_group_id += 1

    def get_root_group_id(self) -> Optional[int]:
        """Return the root group id, or None if no groups."""
        return self.root_group_id

    def set_root_group_id(self, group_id: Optional[int]):
        """Set the root group id."""
        if group_id is None or 0 <= group_id < len(self.groups):
            self.root_group_id = group_id

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, index: int) -> CompositionGroup:
        return self.groups[index]

    def __repr__(self):
        return f"GroupManager(groups={len(self.groups)}, root={self.root_group_id})"
