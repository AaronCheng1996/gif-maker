import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel

from src.widgets.tab_rail import (TabRail, ToolTabs, distribute, plan_rows,
                                  OVERFLOW_WIDTH)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


LABELS = ["Composer", "Tile Splitter", "Batch Processor", "GIF Optimizer",
          "Video to GIF", "Clip to GIF", "Image Merge", "Spine to GIF",
          "Crop GIF", "Atlas Unpack", "GIF to Video"]


def _rail(qapp, labels=LABELS, width=1600):
    rail = TabRail()
    rail.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    rail.show()
    for text in labels:
        rail.add_tab(text)
    rail.setFixedWidth(width)
    qapp.processEvents()
    rail._relayout()
    qapp.processEvents()
    return rail


def _shown(rail):
    return rail.count() - len(rail._hidden)


def _widths_for(qapp):
    """Derive test widths from the font actually in use, not from fixed numbers.

    Hard-coded pixel widths make these tests a report on the machine's font
    rather than on the layout rules."""
    rail = _rail(qapp, width=4000)
    mins = rail._minimum_widths()
    return {
        "one_row": sum(mins) + 50,
        # Too narrow for one row, wide enough that some cut leaves both halves fitting.
        "two_rows": sum(mins) // 2 + max(mins),
        # Two rows of this cannot come close to the total, so tabs must be dropped.
        "overflow": max(mins) + OVERFLOW_WIDTH + 10,
    }


def _row_widths(rail):
    """Total pixels each row actually occupies, menu button included."""
    totals = []
    for row in rail._rows:
        total = 0
        for slot in row:
            if rail._hidden and slot == _shown(rail):
                total += rail._overflow.width()
            else:
                total += rail._buttons[slot].width()
        totals.append(total)
    return totals


# ── distribute ───────────────────────────────────────────────────────────

def test_an_even_split_when_nothing_is_starving():
    assert distribute([100, 100, 100], 900) == [300, 300, 300]


def test_a_wide_label_keeps_what_it_needs_and_the_rest_split_the_remainder():
    """An even share is only even among the tabs that can live with it."""
    assert distribute([500, 100, 100], 900) == [500, 200, 200]


def test_taking_one_tab_out_lowers_the_share_for_everyone_left():
    """Two passes are needed here: 480 clears the first share but not the second."""
    widths = distribute([600, 480, 100, 100], 1000)
    assert widths[0] == 600 and widths[1] == 480
    assert widths[2] == widths[3] == 100          # only their minimum was left


def test_every_pixel_of_the_row_is_used():
    for width in (1000, 1001, 1002, 1003):
        assert sum(distribute([100, 100, 100], width)) == width


def test_nothing_is_squeezed_below_its_minimum():
    """The row overflows rather than rendering labels no one can read."""
    assert distribute([100, 100, 100], 100) == [100, 100, 100]


# ── plan_rows ────────────────────────────────────────────────────────────

def test_one_row_while_they_still_fit():
    assert plan_rows([100] * 4, 400) == [[0, 1, 2, 3]]


def test_a_second_row_opens_balanced_rather_than_packed():
    """Greedy packing would leave a stub row with one stretched tab."""
    assert plan_rows([100] * 4, 250) == [[0, 1], [2, 3]]


def test_a_wide_first_tab_can_own_a_row_by_itself():
    assert plan_rows([300, 100, 100, 100], 400) == [[0], [1, 2, 3]]


def test_no_plan_when_two_rows_cannot_hold_them():
    assert plan_rows([100] * 4, 150) is None


# ── the rail ─────────────────────────────────────────────────────────────

def test_tabs_divide_the_whole_width(qapp):
    width = _widths_for(qapp)["two_rows"]
    rail = _rail(qapp, width=width)
    for total in _row_widths(rail):
        assert total == width, "a row left dead space at its end"


def test_no_tab_is_narrower_than_its_own_label(qapp):
    rail = _rail(qapp, width=_widths_for(qapp)["two_rows"])
    mins = rail._minimum_widths()
    for i in range(_shown(rail)):
        assert rail._buttons[i].width() >= mins[i]


def test_one_row_when_there_is_room_for_one(qapp):
    rail = _rail(qapp, width=_widths_for(qapp)["one_row"])
    assert len(rail._rows) == 1
    assert _shown(rail) == len(LABELS)
    assert not rail._overflow.isVisible()


def test_a_second_row_appears_instead_of_shrinking_the_labels(qapp):
    widths = _widths_for(qapp)
    rail = _rail(qapp, width=widths["two_rows"])
    assert len(rail._rows) == 2
    assert _shown(rail) == len(LABELS), "nothing should be dropped yet"
    assert rail.height() > _rail(qapp, width=widths["one_row"]).height()


def test_what_will_not_fit_in_two_rows_moves_into_the_menu(qapp):
    rail = _rail(qapp, width=_widths_for(qapp)["overflow"])
    assert len(rail._rows) <= 2
    assert _shown(rail) < len(LABELS)
    assert rail._overflow.isVisible()
    # dropped from the end, so the hidden ones are the trailing tabs
    assert rail._hidden == list(range(_shown(rail), len(LABELS)))


def test_the_menu_button_marks_itself_when_the_open_tab_is_hidden(qapp):
    rail = _rail(qapp, width=_widths_for(qapp)["overflow"])
    hidden = rail._hidden[0]
    rail.set_current_index(hidden)
    assert rail._overflow.isChecked()
    rail.set_current_index(0)
    assert not rail._overflow.isChecked()


def test_one_tab_survives_even_when_nothing_fits(qapp):
    rail = _rail(qapp, width=120)
    assert _shown(rail) >= 1
    assert rail._overflow.isVisible()


def test_selecting_a_tab_reports_its_index(qapp):
    rail = _rail(qapp)
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.set_current_index(3)
    assert seen == [3]
    rail.set_current_index(3)
    assert seen == [3], "re-selecting the open tab should not re-emit"


# ── ToolTabs, standing in for QTabWidget ─────────────────────────────────

def test_the_page_follows_the_tab(qapp):
    tabs = ToolTabs()
    tabs.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    tabs.show()
    pages = [QLabel(f"page {i}") for i in range(3)]
    for i, page in enumerate(pages):
        tabs.addTab(page, f"Tab {i}")
    qapp.processEvents()

    tabs.setCurrentIndex(2)
    qapp.processEvents()
    assert tabs.currentIndex() == 2
    assert tabs.currentWidget() is pages[2]


def test_it_answers_the_questions_the_app_asks_a_qtabwidget(qapp):
    tabs = ToolTabs()
    tabs.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    tabs.show()
    first, second = QLabel("a"), QLabel("b")
    assert tabs.addTab(first, "First") == 0
    assert tabs.addTab(second, "Second") == 1

    assert tabs.count() == 2
    assert tabs.widget(1) is second
    assert tabs.indexOf(second) == 1
    assert tabs.tabText(0) == "First"
    tabs.setTabText(0, "Renamed")
    assert tabs.tabText(0) == "Renamed"
    tabs.setTabPosition(None)          # accepted, and does nothing


def test_the_first_tab_added_is_the_one_showing(qapp):
    tabs = ToolTabs()
    tabs.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    tabs.show()
    page = QLabel("only")
    tabs.addTab(page, "Only")
    qapp.processEvents()
    assert tabs.currentIndex() == 0
    assert tabs.currentWidget() is page
