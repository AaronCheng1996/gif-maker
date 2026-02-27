import pytest

from PyQt6.QtWidgets import QApplication
from src.main import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_window_group_manager_initialized(qapp):
    """MainWindow should start with a root CompositionGroup in group_manager."""
    from src.core.group_manager import GroupManager
    from src.core.composition_group import CompositionGroup

    window = MainWindow()
    assert isinstance(window.group_manager, GroupManager)
    assert len(window.group_manager.groups) >= 1
    assert isinstance(window.group_manager.groups[0], CompositionGroup)
    root_id = window.group_manager.get_root_group_id()
    assert root_id is not None


def test_template_save_and_apply_roundtrip(qapp):
    """Save the current composition as a template, apply it back, verify group count preserved."""
    from src.core.composition_group import FrameEntry
    from src.core.template_manager import TemplateManager

    window = MainWindow()
    # Add an entry to the root group so it has content
    root_gid = window.group_manager.get_root_group_id()
    root = window.group_manager.get_group(root_gid)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))

    groups_before = len(window.group_manager.groups)

    # Export
    tpl = TemplateManager.export_composition_template(window.group_manager)
    assert tpl["format"] == "composition_group"

    # Import back
    gm2, settings = TemplateManager.import_composition_template(tpl)
    assert len(gm2.groups) == groups_before

