from src.core.sequence_editor import SequenceEditor


def test_add_and_lengths():
    se = SequenceEditor()
    se.add_frame(1, 100)
    se.add_frame(2, 120)
    assert len(se) == 2
    assert se.get_frame_count() == 2
    assert se.get_total_duration() == 220


def test_insert_remove_move_duplicate():
    se = SequenceEditor()
    for i in range(3):
        se.add_frame(i, 100 + i)
    se.insert_frame(1, 99, 200)
    assert [f.material_index for f in se.get_frames()] == [0, 99, 1, 2]
    se.move_frame(3, 1)
    assert [f.material_index for f in se.get_frames()] == [0, 2, 99, 1]
    se.duplicate_frame(2)
    assert [f.material_index for f in se.get_frames()][2:4] == [99, 99]
    se.remove_frame(0)
    assert [f.material_index for f in se.get_frames()][0] == 2


def test_set_durations_and_export():
    se = SequenceEditor()
    se.set_sequence_from_pattern([1, 2, 3], duration=50)
    assert se.export_pattern() == [1, 2, 3]
    assert se.export_durations() == [50, 50, 50]
    se.set_frame_duration(1, 200)
    assert se.export_durations()[1] == 200
    se.set_all_durations(10)
    assert se.export_durations() == [10, 10, 10]


