import os
import pytest

from PyQt6.QtWidgets import QApplication

from src.main import MainWindow
from PyQt6.QtCore import QItemSelectionModel
from src.core import TimelineFrame


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_add_to_current_timeline_extends_timebase_and_uses_sorted_indices(qapp):
    window = MainWindow()

    # Ensure two timelines exist (Main + another)
    if len(window.multi_editor.timelines) < 1:
        window.multi_editor.add_timeline("Main")
        window.multi_editor.set_main_timeline(0)
    if len(window.multi_editor.timelines) < 2:
        window.multi_editor.add_timeline("Layer 2")
    window.refresh_timeline()

    # Add materials in order B, A, C (indices 0,1,2)
    from PIL import Image
    window.material_manager.clear()
    window.material_manager.add_material(Image.new('RGBA', (8, 8), (255, 0, 0, 255)), "B")
    window.material_manager.add_material(Image.new('RGBA', (8, 8), (0, 255, 0, 255)), "A")
    window.material_manager.add_material(Image.new('RGBA', (8, 8), (0, 0, 255, 255)), "C")
    window.refresh_materials_list()

    # Sort Z→A so view order becomes C(2), B(0), A(1)
    window.material_sort_combo.setCurrentText("Name (Z→A)")
    window.refresh_materials_list()

    # Select first two visible materials in the list (C and B)
    window.materials_list.clearSelection()
    if window.materials_list.count() >= 2:
        window.materials_list.item(0).setSelected(True)
        window.materials_list.item(1).setSelected(True)

    # Switch to second timeline tab (non-main)
    non_main_index = 1 if window.multi_editor.main_timeline_index == 0 else 0
    window.timeline_tabs.setCurrentIndex(non_main_index)
    window.refresh_timeline()

    # Execute: add to current timeline
    window.add_selected_to_current_timeline()

    # Assert timebase extended to 2, and materials assigned using underlying indices [2, 0]
    assert window.multi_editor.get_frame_count() >= 2
    tl = window.multi_editor.get_timeline(non_main_index)
    assert tl is not None
    assert tl.frames[0].material_index == 2
    assert tl.frames[1].material_index == 0


def test_reverse_selected_frames_main_vs_non_main(qapp):
    window = MainWindow()

    # Setup: two timelines and 4 timebase frames
    window.multi_editor.timelines.clear()
    a = window.multi_editor.add_timeline("Main")
    window.multi_editor.set_main_timeline(a)
    b = window.multi_editor.add_timeline("Layer")
    window.multi_editor.durations_ms = [100, 200, 300, 400]
    # Ensure frames exist
    for t in window.multi_editor.timelines:
        t.frames = [TimelineFrame(i, 0, 0) for i in [0, 1, 2, 3]]
    # Make the non-main timeline identifiable
    window.multi_editor.timelines[b].frames = [TimelineFrame(i + 10, 0, 0) for i in [0, 1, 2, 3]]

    # MAIN timeline: select rows 1 and 3, reverse
    window.timeline_tabs.setCurrentIndex(window.multi_editor.main_timeline_index)
    window.refresh_timeline()
    tab = window.timeline_tabs.widget(window.multi_editor.main_timeline_index)
    tw = tab.timeline_widget
    tw.timeline_table.clearSelection()
    sel_model = tw.timeline_table.selectionModel()
    idx1 = tw.timeline_table.model().index(1, 0)
    idx3 = tw.timeline_table.model().index(3, 0)
    sel_model.select(idx1, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    sel_model.select(idx3, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    window.reverse_selected_frames()

    # Durations swapped at positions 1 and 3
    assert window.multi_editor.durations_ms == [100, 400, 300, 200]
    # Frames swapped for both timelines
    assert [f.material_index for f in window.multi_editor.timelines[a].frames] == [0, 3, 2, 1]
    assert [f.material_index for f in window.multi_editor.timelines[b].frames] == [10, 13, 12, 11]

    # NON-MAIN timeline: select rows 0 and 2 on non-main, reverse
    window.timeline_tabs.setCurrentIndex(b)
    window.refresh_timeline()
    tab2 = window.timeline_tabs.widget(b)
    tw2 = tab2.timeline_widget
    tw2.timeline_table.clearSelection()
    sel_model2 = tw2.timeline_table.selectionModel()
    idx0 = tw2.timeline_table.model().index(0, 0)
    idx2 = tw2.timeline_table.model().index(2, 0)
    sel_model2.select(idx0, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    sel_model2.select(idx2, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    window.reverse_selected_frames()

    # Durations unchanged
    assert window.multi_editor.durations_ms == [100, 400, 300, 200]
    # Only non-main frames swapped at 0 and 2
    assert [f.material_index for f in window.multi_editor.timelines[a].frames] == [0, 3, 2, 1]
    assert [f.material_index for f in window.multi_editor.timelines[b].frames] == [12, 13, 10, 11]


def test_material_name_appears_in_timeline_text(qapp):
    window = MainWindow()

    # Ensure at least one timeline and one frame
    if not window.multi_editor.timelines:
        window.multi_editor.add_timeline("Main")
        window.multi_editor.set_main_timeline(0)
    window.multi_editor.durations_ms = [100]
    window.multi_editor.timelines[0].frames = [TimelineFrame(None, 0, 0)]

    # Add a material and assign to frame 0
    from PIL import Image
    window.material_manager.clear()
    window.material_manager.add_material(Image.new('RGBA', (8, 8), (1, 2, 3, 255)), "FooMat")
    window.multi_editor.timelines[0].frames[0].material_index = 0

    window.refresh_timeline()
    tab = window.timeline_tabs.widget(window.multi_editor.main_timeline_index)
    tw = tab.timeline_widget
    text = tw.timeline_table.item(0, 2).text()
    assert "[0] FooMat" in text

