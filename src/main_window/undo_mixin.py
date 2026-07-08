from ..core import TemplateManager


class UndoMixin:
    """Snapshot-based undo/redo for the group composition (debounced push)."""

    def _make_snapshot(self) -> dict:
        """Serialize current GroupManager state into a snapshot dict."""
        return {
            "snapshot": TemplateManager.export_composition_template(self.group_manager),
            "current_group_id": self.current_group_id,
        }

    def _capture_initial_snapshot(self):
        """Store the very first snapshot so Undo can return to initial state."""
        self._undo_stack = [self._make_snapshot()]
        self._redo_stack = []

    def _push_undo_snapshot(self):
        """Called by debounce timer: push current state onto undo stack."""
        if self._undo_in_progress:
            return
        snap = self._make_snapshot()
        self._undo_stack.append(snap)
        # Keep stack bounded
        if len(self._undo_stack) > self._MAX_UNDO + 1:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_snapshot(self, snap: dict):
        """Restore GroupManager and UI from a snapshot dict."""
        self._undo_in_progress = True
        try:
            new_gm, _ = TemplateManager.import_composition_template(snap["snapshot"])
            self.group_manager = new_gm
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            gid = snap.get("current_group_id")
            if gid is not None and self.group_manager.get_group(gid) is not None:
                self.current_group_id = gid
            else:
                self.current_group_id = self.group_manager.get_root_group_id()
            self.update_preview()
            self._update_status_labels()
        finally:
            self._undo_in_progress = False

    def undo(self):
        """Restore the previous composition state (Ctrl+Z)."""
        # Need at least 2 entries: [initial, current] to undo one step
        if len(self._undo_stack) < 2:
            self._status("Nothing to undo")
            return
        # Push current state to redo before restoring
        self._redo_stack.append(self._undo_stack.pop())
        self._restore_snapshot(self._undo_stack[-1])
        self._status(f"Undo  ({len(self._undo_stack) - 1} step(s) remain)")

    def redo(self):
        """Re-apply the next composition state (Ctrl+Y / Ctrl+Shift+Z)."""
        if not self._redo_stack:
            self._status("Nothing to redo")
            return
        snap = self._redo_stack.pop()
        self._undo_stack.append(snap)
        self._restore_snapshot(snap)
        self._status(f"Redo  ({len(self._redo_stack)} step(s) available)")
