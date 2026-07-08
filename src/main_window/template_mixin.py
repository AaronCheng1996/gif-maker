from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QListWidgetItem
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

from ..core import TemplateManager


class TemplateMixin:
    """Template save/apply/import/export, template list rendering, and auto-save."""

    def _make_group_thumbnail(self, group_manager, group_id, material_manager, size: int = 48) -> Optional[QIcon]:
        """Render the first frame of the given group as a small QIcon, or None if unavailable."""
        if group_id is None:
            return None
        try:
            frames = self.gif_builder.get_preview_frames_for_group(group_id, group_manager, material_manager)
            if not frames:
                return None
            img, _duration = frames[0]
            pixmap = self.create_thumbnail(img, size, size)
            return QIcon(pixmap)
        except Exception:
            return None

    def quick_save_template(self):
        """Save current group composition to in-memory template list (prompts for name)."""
        if len(self.group_manager.groups) == 0:
            QMessageBox.warning(self, "Warning", "No groups to save as template!")
            return
        suggested = f"Template {len(self.templates) + 1}"
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:", text=suggested)
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.templates:
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Template '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_composition_template(
                self.group_manager,
                self.transparent_bg_checkbox.isChecked(),
                color_count,
            )
            self.templates[name] = template
            self.template_thumbnails[name] = self._make_group_thumbnail(
                self.group_manager, self.group_manager.get_root_group_id(), self.material_manager
            )
            self.refresh_template_list()
            info = TemplateManager.get_template_info(template)
            self._status(
                f"Saved '{name}' — {info['group_count']} group(s), "
                f"{info['materials_needed']} material(s) needed"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save template: {str(e)}")

    def quick_apply_template(self):
        """Apply selected in-memory template to current composition."""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to apply!")
            return
        template_name = current_item.text().split(" - ")[0]
        template = self.templates.get(template_name)
        if not template:
            QMessageBox.warning(self, "Warning", "Selected template not found!")
            return
        try:
            new_gm, settings = TemplateManager.import_composition_template(template)
            self.group_manager = new_gm
            if settings:
                self.transparent_bg_checkbox.setChecked(
                    settings.get("transparent_bg", self.transparent_bg_checkbox.isChecked())
                )
                color_count = settings.get("color_count", int(self.color_palette_combo.currentText()))
                self.color_palette_combo.setCurrentText(str(color_count))
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            self.update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply template: {str(e)}")

    def quick_import_template(self):
        """Import a composition template JSON from disk into in-memory templates."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Template", self.last_template_dir, "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            template = TemplateManager.load_template_from_file(file_path)
            TemplateManager.validate_template(template)
            name = Path(file_path).stem
            suffix = 1
            unique_name = name
            while unique_name in self.templates:
                suffix += 1
                unique_name = f"{name} ({suffix})"
            self.templates[unique_name] = template
            try:
                temp_gm, _settings = TemplateManager.import_composition_template(template)
                self.template_thumbnails[unique_name] = self._make_group_thumbnail(
                    temp_gm, temp_gm.get_root_group_id(), self.material_manager
                )
            except Exception:
                self.template_thumbnails[unique_name] = None
            self.refresh_template_list()
            QMessageBox.information(self, "Imported", f"Imported template '{unique_name}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import template: {str(e)}")

    def quick_export_template(self):
        """Export selected in-memory template to a JSON file."""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to export!")
            return
        template_name = current_item.text().split(" - ")[0]
        template = self.templates.get(template_name)
        if not template:
            QMessageBox.warning(self, "Warning", "Selected template not found!")
            return
        default_path = str(Path(self.last_template_dir or ".") / f"{template_name}.json")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            default_path,
            "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            TemplateManager.save_template_to_file(template, file_path)
            QMessageBox.information(self, "Success", f"Exported template to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export template: {str(e)}")

    def remove_template(self):
        """Remove selected template from list"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to remove!")
            return

        template_name = current_item.text().split(" - ")[0]
        if template_name not in self.templates:
            return

        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Remove template '{template_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.templates[template_name]
            self.template_thumbnails.pop(template_name, None)
            self.refresh_template_list()

    def refresh_template_list(self):
        """Refresh template list widget with current in-memory templates."""
        self.template_list.clear()
        for name, tpl in self.templates.items():
            try:
                info = TemplateManager.get_template_info(tpl)
                subtitle = (
                    f"{info.get('group_count', 0)} groups, "
                    f"{info.get('materials_needed', 0)} tiles"
                )
            except Exception:
                subtitle = "invalid"
            item = QListWidgetItem(f"{name} - {subtitle}")
            icon = self.template_thumbnails.get(name)
            if icon is not None:
                item.setIcon(icon)
            self.template_list.addItem(item)
        if hasattr(self, "batch_processor"):
            self.batch_processor.set_templates(self.templates)
        if hasattr(self, "template_preview_label"):
            self._on_template_selection_changed(self.template_list.currentItem(), None)

    def _on_template_selection_changed(self, current, _previous=None):
        """Update the larger preview label to match the selected template's thumbnail."""
        if not hasattr(self, 'template_preview_label'):
            return
        if current is None:
            self.template_preview_label.clear()
            return
        name = current.text().split(" - ")[0]
        icon = self.template_thumbnails.get(name)
        if icon is not None:
            self.template_preview_label.setPixmap(icon.pixmap(QSize(64, 64)))
        else:
            self.template_preview_label.clear()

    def auto_save_template(self):
        """Automatically save current composition as a template."""
        if not self.auto_save_enabled:
            return
        if len(self.group_manager.groups) == 0:
            return
        try:
            content_hash = self._get_content_hash()
            if content_hash == self.last_auto_save_content_hash:
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_composition_template(
                self.group_manager,
                self.transparent_bg_checkbox.isChecked(),
                color_count,
            )
            template["auto_save_metadata"] = {
                "timestamp": timestamp,
                "group_count": len(self.group_manager.groups),
                "material_count": len(self.material_manager),
                "content_hash": content_hash,
            }
            TemplateManager.save_template_to_file(template, str(self.auto_save_file))
            self.last_auto_save_content_hash = content_hash
            ts = datetime.now().strftime("%H:%M:%S")
            if hasattr(self, '_status_autosave_label'):
                self._status_autosave_label.setText(f"Auto-saved {ts}")
        except Exception as e:
            print(f"Auto-save failed: {e}")

    def _get_content_hash(self):
        """Hash current group composition for change detection."""
        import hashlib
        try:
            template = TemplateManager.export_composition_template(self.group_manager)
            import json as _json
            content = _json.dumps(template, sort_keys=True)
        except Exception:
            content = str(id(self.group_manager))
        return hashlib.md5(content.encode()).hexdigest()

    def restore_auto_save(self):
        """Restore composition from the latest auto-save."""
        try:
            if not self.auto_save_file.exists():
                QMessageBox.information(self, "No Auto-Save", "No auto-save file found.")
                return
            template = TemplateManager.load_template_from_file(str(self.auto_save_file))
            new_gm, settings = TemplateManager.import_composition_template(template)
            self.group_manager = new_gm
            if settings:
                self.transparent_bg_checkbox.setChecked(
                    settings.get("transparent_bg", self.transparent_bg_checkbox.isChecked())
                )
                color_count = settings.get("color_count", int(self.color_palette_combo.currentText()))
                color_text = str(color_count)
                if color_text in [self.color_palette_combo.itemText(i) for i in range(self.color_palette_combo.count())]:
                    self.color_palette_combo.setCurrentText(color_text)
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            self.update_preview()
            metadata = template.get("auto_save_metadata", {})
            QMessageBox.information(
                self, "Auto-Save Restored",
                f"Restored from: {self.auto_save_file.name}\n\n"
                f"Saved: {metadata.get('timestamp', 'unknown')}\n"
                f"Groups: {metadata.get('group_count', len(self.group_manager.groups))}\n"
                f"Materials: {metadata.get('material_count', 0)}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", f"Failed to restore auto-save:\n{str(e)}")

    def toggle_auto_save(self):
        """Toggle auto-save on/off"""
        self.auto_save_enabled = not self.auto_save_enabled
        if self.auto_save_enabled:
            self.auto_save_timer.start(self.auto_save_interval)
            self._status("Auto-save enabled")
        else:
            self.auto_save_timer.stop()
            self._status("Auto-save disabled")
        self._update_status_labels()
