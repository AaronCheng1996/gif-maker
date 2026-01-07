import os
import pytest

from PyQt6.QtWidgets import QApplication

from src.main import MainWindow
from PyQt6.QtCore import QItemSelectionModel
from src.core import LayerFrame


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_add_to_current_layer_extends_timebase_and_uses_sorted_indices(qapp):
    window = MainWindow()

    # Ensure two layer tracks exist (Main + another)
    if len(window.layer_editor.layer_tracks) < 1:
        window.layer_editor.add_layer_track("Main")
        window.layer_editor.set_main_layer_track(0)
    if len(window.layer_editor.layer_tracks) < 2:
        window.layer_editor.add_layer_track("Layer 2")
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

    # Switch to second layer track tab (non-main)
    non_main_index = 1 if window.layer_editor.main_track_index == 0 else 0
    window.timeline_tabs.setCurrentIndex(non_main_index)
    window.refresh_timeline()

    # Execute: add to current layer
    window.add_selected_to_current_timeline()

    # Assert timebase extended to 2, and materials assigned using underlying indices [2, 0]
    assert window.layer_editor.get_frame_count() >= 2
    tl = window.layer_editor.get_layer_track(non_main_index)
    assert tl is not None
    assert tl.frames[0].material_index == 2
    assert tl.frames[1].material_index == 0


def test_reverse_selected_frames_main_vs_non_main(qapp):
    window = MainWindow()

    # Setup: two layer tracks and 4 timebase frames
    window.layer_editor.layer_tracks.clear()
    a = window.layer_editor.add_layer_track("Main")
    window.layer_editor.set_main_track(a)
    b = window.layer_editor.add_layer_track("Layer")
    window.layer_editor.durations_ms = [100, 200, 300, 400]
    # Ensure frames exist
    for t in window.layer_editor.layer_tracks:
        t.frames = [LayerFrame(material_index=i, x=0, y=0) for i in [0, 1, 2, 3]]
    # Make the non-main layer track identifiable
    window.layer_editor.layer_tracks[b].frames = [LayerFrame(material_index=i + 10, x=0, y=0) for i in [0, 1, 2, 3]]

    # MAIN layer track: select rows 1 and 3, reverse
    window.timeline_tabs.setCurrentIndex(window.layer_editor.main_track_index)
    window.refresh_timeline()
    tab = window.timeline_tabs.widget(window.layer_editor.main_track_index)
    tw = tab.timeline_widget
    tw.timeline_table.clearSelection()
    sel_model = tw.timeline_table.selectionModel()
    idx1 = tw.timeline_table.model().index(1, 0)
    idx3 = tw.timeline_table.model().index(3, 0)
    sel_model.select(idx1, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    sel_model.select(idx3, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    window.reverse_selected_frames()

    # Durations swapped at positions 1 and 3
    assert window.layer_editor.durations_ms == [100, 400, 300, 200]
    # Frames swapped for both layer tracks
    assert [f.material_index for f in window.layer_editor.layer_tracks[a].frames] == [0, 3, 2, 1]
    assert [f.material_index for f in window.layer_editor.layer_tracks[b].frames] == [10, 13, 12, 11]

    # NON-MAIN layer track: select rows 0 and 2 on non-main, reverse
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
    assert window.layer_editor.durations_ms == [100, 400, 300, 200]
    # Only non-main frames swapped at 0 and 2
    assert [f.material_index for f in window.layer_editor.layer_tracks[a].frames] == [0, 3, 2, 1]
    assert [f.material_index for f in window.layer_editor.layer_tracks[b].frames] == [12, 13, 10, 11]


def test_material_name_appears_in_timeline_text(qapp):
    window = MainWindow()

    # Ensure at least one layer track and one frame
    if not window.layer_editor.layer_tracks:
        window.layer_editor.add_layer_track("Main")
        window.layer_editor.set_main_track(0)
    window.layer_editor.durations_ms = [100]
    window.layer_editor.layer_tracks[0].frames = [LayerFrame(material_index=None, x=0, y=0)]

    # Add a material and assign to frame 0
    from PIL import Image
    window.material_manager.clear()
    window.material_manager.add_material(Image.new('RGBA', (8, 8), (1, 2, 3, 255)), "FooMat")
    window.layer_editor.layer_tracks[0].frames[0].material_index = 0

    window.refresh_timeline()
    tab = window.timeline_tabs.widget(window.layer_editor.main_track_index)
    tw = tab.timeline_widget
    text = tw.timeline_table.item(0, 2).text()
    assert "[0] FooMat" in text

