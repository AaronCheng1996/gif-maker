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


def test_material_group_independent_offsets_basic():
    """Test material_offsets attribute initialization and basic operations"""
    # Test default initialization
    group = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Test Group",
        independent_offsets=False
    )
    
    assert not group.independent_offsets
    assert len(group.material_offsets) == 0
    
    # Test with independent_offsets enabled
    group_independent = MaterialGroup(
        material_indices=[3, 4, 5],
        frame_duration=150,
        loop_count=2,
        name="Independent Group",
        independent_offsets=True
    )
    
    assert group_independent.independent_offsets
    assert len(group_independent.material_offsets) == 0  # Empty by default


def test_material_group_set_get_offsets():
    """Test setting and getting individual material offsets"""
    group = MaterialGroup(
        material_indices=[10, 11, 12],
        frame_duration=100,
        loop_count=1,
        name="Offset Test",
        independent_offsets=True
    )
    
    # Set offsets
    group.set_material_offset(0, 10, 20)
    group.set_material_offset(1, 30, 40)
    group.set_material_offset(2, 50, 60)
    
    # Get offsets
    assert group.get_material_offset(0) == (10, 20)
    assert group.get_material_offset(1) == (30, 40)
    assert group.get_material_offset(2) == (50, 60)
    
    # Get offset for non-existent index (should return default)
    assert group.get_material_offset(5) == (0, 0)


def test_material_group_offsets_only_when_independent():
    """Test that offsets can only be set when independent_offsets is True"""
    group_unified = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Unified Group",
        independent_offsets=False
    )
    
    # Try to set offset (should not work)
    group_unified.set_material_offset(0, 100, 200)
    
    # Should remain empty because independent_offsets is False
    assert len(group_unified.material_offsets) == 0
    assert group_unified.get_material_offset(0) == (0, 0)


def test_material_group_clear_offsets():
    """Test clearing all material offsets"""
    group = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Clear Test",
        independent_offsets=True
    )
    
    # Set some offsets
    group.set_material_offset(0, 10, 20)
    group.set_material_offset(1, 30, 40)
    
    assert len(group.material_offsets) == 2
    
    # Clear all offsets
    group.clear_material_offsets()
    
    assert len(group.material_offsets) == 0
    assert group.get_material_offset(0) == (0, 0)
    assert group.get_material_offset(1) == (0, 0)


def test_material_group_offsets_serialization():
    """Test that material_offsets are properly serialized and deserialized"""
    # Create group with offsets
    group = MaterialGroup(
        material_indices=[0, 1, 2, 3],
        frame_duration=100,
        loop_count=2,
        name="Serialization Test",
        independent_offsets=True
    )
    
    group.set_material_offset(0, 10, 20)
    group.set_material_offset(1, 30, 40)
    group.set_material_offset(3, 70, 80)  # Skip index 2
    
    # Serialize
    data = group.to_dict()
    
    assert "independent_offsets" in data
    assert data["independent_offsets"] == True
    assert "material_offsets" in data
    assert len(data["material_offsets"]) == 3
    
    # Check serialized format (keys should be strings)
    assert "0" in data["material_offsets"]
    assert data["material_offsets"]["0"] == [10, 20]
    assert data["material_offsets"]["1"] == [30, 40]
    assert data["material_offsets"]["3"] == [70, 80]
    
    # Deserialize
    restored = MaterialGroup.from_dict(data)
    
    assert restored.independent_offsets == True
    assert restored.get_material_offset(0) == (10, 20)
    assert restored.get_material_offset(1) == (30, 40)
    assert restored.get_material_offset(2) == (0, 0)  # Not set
    assert restored.get_material_offset(3) == (70, 80)


def test_material_group_offsets_not_serialized_when_unified():
    """Test that material_offsets are not included in serialization for unified mode"""
    group = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Unified Test",
        independent_offsets=False
    )
    
    # Serialize
    data = group.to_dict()
    
    # material_offsets should not be in the dict for unified mode
    assert "material_offsets" not in data


def test_material_group_offsets_backward_compatibility():
    """Test that old templates without material_offsets still load correctly"""
    # Simulate old template data without material_offsets
    old_data = {
        "name": "Old Group",
        "material_indices": [0, 1, 2],
        "frame_duration": 100,
        "loop_count": 2,
        "independent_offsets": True
    }
    
    # Should load without error
    group = MaterialGroup.from_dict(old_data)
    
    assert group.independent_offsets == True
    assert len(group.material_offsets) == 0
    assert group.get_material_offset(0) == (0, 0)


def test_material_group_copy_includes_offsets():
    """Test that copy() includes material_offsets"""
    original = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Original",
        independent_offsets=True
    )
    
    original.set_material_offset(0, 10, 20)
    original.set_material_offset(1, 30, 40)
    
    # Copy
    copied = original.copy()
    
    assert copied.independent_offsets == True
    assert copied.get_material_offset(0) == (10, 20)
    assert copied.get_material_offset(1) == (30, 40)
    
    # Modify copy, should not affect original
    copied.set_material_offset(0, 99, 99)
    
    assert original.get_material_offset(0) == (10, 20)  # Unchanged
    assert copied.get_material_offset(0) == (99, 99)  # Changed