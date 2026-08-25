"""A tab strip that shares the window's width instead of hugging its labels.

QTabBar lays every tab out on one line and, when they stop fitting, either
scrolls them behind arrows or squeezes them until the labels are unreadable.
Neither is much use with eleven tools: the last ones end up off-screen or
illegible. There is no way to make QTabBar wrap — its geometry is computed
privately and `tabRect` is not virtual — so the strip here is its own widget and
`ToolTabs` puts it back together with a QStackedWidget, keeping the slice of
QTabWidget's API the app actually uses.

The rules it follows, in order:

1. tabs divide the available width evenly;
2. no tab is narrower than its own label needs, so an even share is only even
   among the tabs that can take it — wider labels keep what they require and the
   rest split what is left;
3. when one row cannot hold them all, a second row opens and the split point is
   chosen to balance the two rows rather than to pack the first one full;
4. when two rows still cannot, the tabs that do not fit are dropped from the end
   and reachable through a trailing menu button.
"""
from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (QWidget, QPushButton, QStackedWidget, QVBoxLayout,
                             QMenu, QSizePolicy)

# Room for the label plus the breathing space the tab style asks for. This is a
# floor, not a target: a tab is never squeezed below it, which is what keeps
# labels readable when the window gets narrow.
TAB_PADDING = 24
TAB_MIN_WIDTH = 64
TAB_HEIGHT = 38
MAX_ROWS = 2
OVERFLOW_TEXT = "…"       # …
OVERFLOW_WIDTH = 40


def distribute(mins: Sequence[int], width: int) -> List[int]:
    """Split `width` as evenly as possible without starving any tab.

    An even share is only even among tabs that can live with it. Anything whose
    minimum is wider than the share takes its minimum and drops out, and the
    share is recomputed for the rest — repeatedly, because taking one tab out
    lowers the share for everyone left.
    """
    n = len(mins)
    if n == 0:
        return []
    widths = [0] * n
    pending = set(range(n))
    available = width

    while pending:
        share = available // len(pending)
        greedy = [i for i in pending if mins[i] > share]
        if not greedy:
            # Whole pixels only, so hand the remainder out one each from the
            # left rather than leaving a gap at the end of the row.
            leftover = available - share * len(pending)
            for rank, i in enumerate(sorted(pending)):
                widths[i] = share + (1 if rank < leftover else 0)
            break
        for i in greedy:
            widths[i] = mins[i]
            available -= mins[i]
            pending.discard(i)

    return widths


def plan_rows(mins: Sequence[int], width: int) -> Optional[List[List[int]]]:
    """Group tab indices into at most MAX_ROWS rows, or None if they don't fit.

    With two rows there are only n-1 places to break, so every one is tried and
    the most balanced feasible break wins. Filling the first row greedily would
    fit just as many tabs but leave a stub second row, where one tab stretches
    across the whole window.
    """
    n = len(mins)
    if n == 0:
        return []
    if width <= 0:
        return None
    if sum(mins) <= width:
        return [list(range(n))]

    best: Optional[Tuple[int, List[List[int]]]] = None
    for cut in range(1, n):
        head, tail = sum(mins[:cut]), sum(mins[cut:])
        if head > width or tail > width:
            continue
        imbalance = abs(head - tail)
        if best is None or imbalance < best[0]:
            best = (imbalance, [list(range(cut)), list(range(cut, n))])
    return best[1] if best else None


class TabRail(QWidget):
    """The strip of tab buttons. Emits `currentChanged` with the tab's index."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tabRail")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._labels: List[str] = []
        self._buttons: List[QPushButton] = []
        self._current = -1
        self._rows: List[List[int]] = []
        self._hidden: List[int] = []

        self._overflow = QPushButton(OVERFLOW_TEXT, self)
        self._overflow.setObjectName("tabOverflow")
        self._overflow.setToolTip("More tabs")
        self._overflow.setCheckable(True)
        self._overflow.clicked.connect(self._show_overflow_menu)
        self._overflow.hide()

        self.setFixedHeight(TAB_HEIGHT)

    # ── contents ─────────────────────────────────────────────────────────
    def add_tab(self, text: str) -> int:
        button = QPushButton(text, self)
        button.setObjectName("tabButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        index = len(self._buttons)
        button.clicked.connect(lambda _checked, i=index: self.set_current_index(i))
        self._labels.append(text)
        self._buttons.append(button)
        if self._current < 0:
            self.set_current_index(0)
        self._relayout()
        return index

    def count(self) -> int:
        return len(self._buttons)

    def tab_text(self, index: int) -> str:
        return self._labels[index] if 0 <= index < len(self._labels) else ""

    def set_tab_text(self, index: int, text: str):
        if 0 <= index < len(self._labels):
            self._labels[index] = text
            self._relayout()

    def current_index(self) -> int:
        return self._current

    def set_current_index(self, index: int):
        if not (0 <= index < len(self._buttons)) or index == self._current:
            self._sync_checked()
            return
        self._current = index
        self._sync_checked()
        self.currentChanged.emit(index)

    def _sync_checked(self):
        for i, button in enumerate(self._buttons):
            button.setChecked(i == self._current)
        self._overflow.setChecked(self._current in self._hidden)

    # ── measuring ────────────────────────────────────────────────────────
    def _minimum_widths(self) -> List[int]:
        fm = QFontMetrics(self.font())
        return [max(TAB_MIN_WIDTH, fm.horizontalAdvance(text) + TAB_PADDING)
                for text in self._labels]

    def minimumSizeHint(self) -> QSize:
        # One tab's worth. Anything narrower is the caller's choice, and the
        # labels elide rather than spill.
        mins = self._minimum_widths()
        return QSize(min(mins) if mins else TAB_MIN_WIDTH, TAB_HEIGHT)

    def sizeHint(self) -> QSize:
        mins = self._minimum_widths()
        return QSize(sum(mins) if mins else TAB_MIN_WIDTH,
                     TAB_HEIGHT * max(1, len(self._rows) or 1))

    # ── layout ───────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        if not self._buttons:
            self._overflow.hide()
            return

        width = max(0, self.width())
        mins = self._minimum_widths()

        # Drop tabs off the end until what is left fits in two rows. The menu
        # button has to be paid for out of the same width, so it joins the last
        # row as one more item competing for space.
        shown = len(mins)
        rows: Optional[List[List[int]]] = plan_rows(mins, width)
        while rows is None and shown > 1:
            shown -= 1
            rows = plan_rows(list(mins[:shown]) + [OVERFLOW_WIDTH], width)
        if rows is None:
            rows = [[0]]
            shown = 1

        overflowing = shown < len(mins)
        self._hidden = list(range(shown, len(mins))) if overflowing else []
        row_mins = list(mins[:shown]) + ([OVERFLOW_WIDTH] if overflowing else [])
        self._rows = rows

        for i, button in enumerate(self._buttons):
            button.setVisible(i < shown)
        self._overflow.setVisible(overflowing)

        fm = QFontMetrics(self.font())
        y = 0
        for row in rows:
            widths = distribute([row_mins[i] for i in row], width)
            x = 0
            for slot, w in zip(row, widths):
                widget = (self._overflow if overflowing and slot == len(row_mins) - 1
                          else self._buttons[slot])
                widget.setGeometry(x, y, w, TAB_HEIGHT)
                if widget is not self._overflow:
                    label = self._labels[slot]
                    widget.setText(fm.elidedText(label, Qt.TextElideMode.ElideRight,
                                                 max(0, w - TAB_PADDING // 2)))
                x += w
            y += TAB_HEIGHT

        wanted = TAB_HEIGHT * len(rows)
        if self.height() != wanted:
            self.setFixedHeight(wanted)
        self._sync_checked()

    # ── overflow menu ────────────────────────────────────────────────────
    def _show_overflow_menu(self):
        if not self._hidden:
            self._overflow.setChecked(False)
            return
        menu = QMenu(self)
        for i in self._hidden:
            action = menu.addAction(self._labels[i])
            action.setCheckable(True)
            action.setChecked(i == self._current)
            action.triggered.connect(lambda _checked, idx=i: self.set_current_index(idx))
        menu.exec(self._overflow.mapToGlobal(self._overflow.rect().bottomLeft()))
        self._sync_checked()


class ToolTabs(QWidget):
    """A QTabWidget stand-in whose tab strip fills the width and wraps."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rail = TabRail(self)
        self.stack = QStackedWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.rail)
        layout.addWidget(self.stack, 1)

        self.rail.currentChanged.connect(self._on_rail_changed)

    def _on_rail_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        self.currentChanged.emit(index)

    # ── the slice of QTabWidget's API the app uses ───────────────────────
    def addTab(self, widget: QWidget, text: str) -> int:
        self.stack.addWidget(widget)
        return self.rail.add_tab(text)

    def count(self) -> int:
        return self.stack.count()

    def widget(self, index: int) -> Optional[QWidget]:
        return self.stack.widget(index)

    def indexOf(self, widget: QWidget) -> int:
        return self.stack.indexOf(widget)

    def tabText(self, index: int) -> str:
        return self.rail.tab_text(index)

    def setTabText(self, index: int, text: str):
        self.rail.set_tab_text(index, text)

    def currentIndex(self) -> int:
        return self.rail.current_index()

    def setCurrentIndex(self, index: int):
        self.rail.set_current_index(index)

    def currentWidget(self) -> Optional[QWidget]:
        return self.stack.currentWidget()

    def setTabPosition(self, _position):
        """Accepted for compatibility; this strip only sits on top."""
