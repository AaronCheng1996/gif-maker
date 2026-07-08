class StatusMixin:
    """Status bar message helpers."""

    def _status(self, msg: str, timeout_ms: int = 5000):
        """Show a temporary message in the status bar."""
        if hasattr(self, '_status_bar'):
            self._status_bar.showMessage(msg, timeout_ms)

    def _update_status_labels(self):
        """Refresh the permanent status bar labels."""
        if not hasattr(self, '_status_material_label'):
            return
        self._status_material_label.setText(f"Materials: {len(self.material_manager)}")
        # Current group name
        grp = None
        if self.current_group_id is not None:
            grp = self.group_manager.get_group(self.current_group_id)
        self._status_group_label.setText(f"Group: {grp.name if grp else '—'}")
        # Auto-save state (only update text label if not showing "saved HH:MM:SS")
        autosave_txt = self._status_autosave_label.text()
        if autosave_txt in ("Auto-save: ON", "Auto-save: OFF"):
            self._status_autosave_label.setText(
                "Auto-save: ON" if self.auto_save_enabled else "Auto-save: OFF"
            )
