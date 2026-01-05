"""
Tests for MaterialGroup and GroupManager
"""

from src.core.material_group import MaterialGroup
from src.core.group_manager import GroupManager


def test_material_group_basic():
    """Test basic MaterialGroup functionality"""
    group = MaterialGroup(
        material_indices=[0, 1, 2, 3],
        frame_duration=100,
        loop_count=2,
        name="Test Group"
    )
    
    assert group.name == "Test Group"
    assert len(group.material_indices) == 4
    assert group.frame_duration == 100
    assert group.loop_count == 2


def test_material_group_expansion():
    """Test MaterialGroup expansion to frames"""
    group = MaterialGroup(
        material_indices=[1, 2, 3],
        frame_duration=50,
        loop_count=3
    )
    
    frames = group.expand_to_frames()
    assert len(frames) == 9  # 3 materials × 3 loops
    assert frames[0] == (1, 50)
    assert frames[3] == (1, 50)  # First frame of second loop
    assert frames[8] == (3, 50)  # Last frame


def test_material_group_totals():
    """Test total frames and duration calculation"""
    group = MaterialGroup(
        material_indices=[0, 1, 2, 3],
        frame_duration=100,
        loop_count=2
    )
    
    assert group.get_total_frames() == 8  # 4 × 2
    assert group.get_total_duration() == 800  # 8 × 100ms


def test_material_group_get_frame_at_index():
    """Test getting individual frames by index"""
    group = MaterialGroup(
        material_indices=[10, 20, 30],
        frame_duration=75,
        loop_count=2
    )
    
    assert group.get_frame_at_index(0) == (10, 75)
    assert group.get_frame_at_index(2) == (30, 75)
    assert group.get_frame_at_index(3) == (10, 75)  # Second loop
    assert group.get_frame_at_index(5) == (30, 75)


def test_material_group_serialization():
    """Test to_dict and from_dict"""
    original = MaterialGroup(
        material_indices=[5, 6, 7],
        frame_duration=120,
        loop_count=3,
        name="Serialization Test"
    )
    
    data = original.to_dict()
    restored = MaterialGroup.from_dict(data)
    
    assert restored.name == original.name
    assert restored.material_indices == original.material_indices
    assert restored.frame_duration == original.frame_duration
    assert restored.loop_count == original.loop_count


def test_group_manager_basic():
    """Test basic GroupManager functionality"""
    manager = GroupManager()
    
    group1 = MaterialGroup(
        material_indices=[0, 1],
        frame_duration=100,
        loop_count=1,
        name="Group 1"
    )
    
    idx = manager.add_group(group1)
    assert idx == 0
    assert len(manager) == 1
    
    retrieved = manager.get_group(0)
    assert retrieved is not None
    assert retrieved.name == "Group 1"


def test_group_manager_create_from_materials():
    """Test creating group from material indices"""
    manager = GroupManager()
    
    idx = manager.create_group_from_materials(
        material_indices=[10, 20, 30],
        frame_duration=150,
        loop_count=2,
        name="Created Group"
    )
    
    group = manager.get_group(idx)
    assert group is not None
    assert group.name == "Created Group"
    assert group.material_indices == [10, 20, 30]
    assert group.frame_duration == 150
    assert group.loop_count == 2


def test_group_manager_remove_and_clear():
    """Test removing groups"""
    manager = GroupManager()
    
    manager.create_group_from_materials([1, 2], name="G1")
    manager.create_group_from_materials([3, 4], name="G2")
    manager.create_group_from_materials([5, 6], name="G3")
    
    assert len(manager) == 3
    
    manager.remove_group(1)
    assert len(manager) == 2
    assert manager.get_group(0).name == "G1"
    assert manager.get_group(1).name == "G3"
    
    manager.clear()
    assert len(manager) == 0


def test_group_update_materials():
    """Test updating materials in a group"""
    manager = GroupManager()
    idx = manager.create_group_from_materials([1, 2, 3], name="Test")
    
    group = manager.get_group(idx)
    assert group.material_indices == [1, 2, 3]
    
    # Update materials
    group.material_indices = [4, 5, 6, 7]
    manager.groups[idx] = group
    
    # Verify update
    updated = manager.get_group(idx)
    assert updated.material_indices == [4, 5, 6, 7]


def test_batch_material_removal_from_group():
    """Test removing multiple materials from a group at once"""
    manager = GroupManager()
    idx = manager.create_group_from_materials(
        [0, 1, 2, 3, 4, 5, 6],
        name="Large Group"
    )
    
    group = manager.get_group(idx)
    original_count = len(group.material_indices)
    
    # Remove materials at indices 1, 3, 5
    materials_to_remove = [1, 3, 5]
    for mat_idx in materials_to_remove:
        if mat_idx in group.material_indices:
            group.material_indices.remove(mat_idx)
    
    # Update the group
    manager.groups[idx] = group
    
    # Verify removal
    updated = manager.get_group(idx)
    assert len(updated.material_indices) == original_count - 3
    assert 1 not in updated.material_indices
    assert 3 not in updated.material_indices
    assert 5 not in updated.material_indices
    assert 0 in updated.material_indices
    assert 2 in updated.material_indices


def test_empty_group_allowed():
    """Test that groups can be empty (for template workflow)"""
    manager = GroupManager()
    
    # Create empty group
    empty_group = MaterialGroup(
        material_indices=[],
        frame_duration=100,
        loop_count=1,
        name="Empty Group"
    )
    
    idx = manager.add_group(empty_group)
    
    # Verify empty group is stored
    retrieved = manager.get_group(idx)
    assert retrieved is not None
    assert len(retrieved.material_indices) == 0
    assert retrieved.get_total_frames() == 0


def test_group_with_single_material_duration():
    """Test that single-material groups use their frame_duration correctly"""
    group = MaterialGroup(
        material_indices=[22],  # Single material
        frame_duration=2000,    # 2 seconds
        loop_count=1,
        name="Idle"
    )
    
    assert group.get_total_frames() == 1
    assert group.get_total_duration() == 2000
    
    # Expand to frames
    frames = group.expand_to_frames()
    assert len(frames) == 1
    assert frames[0] == (22, 2000)  # material_index, duration
