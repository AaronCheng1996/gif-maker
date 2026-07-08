from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from PIL import Image


class ExportMixin:
    """GIF export for the current group, batch export of all groups, and spritesheet export."""

    _EXPORT_FORMAT_INFO = {
        "GIF":  {"ext": "gif",  "filter": "GIF Files (*.gif)"},
        "APNG": {"ext": "png",  "filter": "APNG Files (*.png)"},
        "WebP": {"ext": "webp", "filter": "WebP Files (*.webp)"},
    }

    def export_gif(self):
        """Export the currently selected group as GIF, APNG, or animated WebP."""
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "No group selected to export!")
            return
        if self.group_manager.get_group(self.current_group_id) is None:
            QMessageBox.warning(self, "Warning", "Selected group not found!")
            return

        fmt = self.export_format_combo.currentText() if hasattr(self, 'export_format_combo') else "GIF"
        info = self._EXPORT_FORMAT_INFO.get(fmt, self._EXPORT_FORMAT_INFO["GIF"])

        default_path = f"output.{info['ext']}"
        if self.last_export_dir:
            default_path = str(Path(self.last_export_dir) / f"output.{info['ext']}")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save GIF",
            default_path,
            info["filter"],
        )

        if file_path:
            try:
                self.last_export_dir = str(Path(file_path).parent)
                self.gif_builder.set_output_size(
                    self.width_spinbox.value(),
                    self.height_spinbox.value()
                )
                self.gif_builder.set_loop(self.loop_spinbox.value())
                color_count = int(self.color_palette_combo.currentText())
                self.gif_builder.set_color_count(color_count)
                if self.transparent_bg_checkbox.isChecked():
                    self.gif_builder.set_background_color(0, 0, 0, 0)
                else:
                    self.gif_builder.set_background_color(255, 255, 255, 255)

                if fmt == "APNG":
                    self.gif_builder.build_apng_from_group(
                        self.current_group_id, self.group_manager, self.material_manager, file_path,
                    )
                elif fmt == "WebP":
                    quality = self.webp_quality_spinbox.value() if hasattr(self, 'webp_quality_spinbox') else 80
                    self.gif_builder.build_webp_from_group(
                        self.current_group_id, self.group_manager, self.material_manager, file_path,
                        quality=quality,
                    )
                else:
                    self.gif_builder.build_gif_from_group(
                        self.current_group_id, self.group_manager, self.material_manager, file_path,
                    )
                QMessageBox.information(self, "Success", f"{fmt} exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export {fmt}:\n{str(e)}")

    # ──────────────────────────────────────────────────────────────
    # Batch Export All Groups
    # ──────────────────────────────────────────────────────────────

    def batch_export_all_groups(self):
        """Export each top-level group as a separate GIF file."""
        groups = self.group_manager.get_all_groups()
        if not groups:
            QMessageBox.warning(self, "Warning", "No groups to export!")
            return
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", self.last_export_dir
        )
        if not export_dir:
            return
        self.last_export_dir = export_dir

        width = self.width_spinbox.value()
        height = self.height_spinbox.value()
        loop = self.loop_spinbox.value()
        color_count = int(self.color_palette_combo.currentText())
        transparent = self.transparent_bg_checkbox.isChecked()

        self.gif_builder.set_output_size(width, height)
        self.gif_builder.set_loop(loop)
        self.gif_builder.set_color_count(color_count)
        if transparent:
            self.gif_builder.set_background_color(0, 0, 0, 0)
        else:
            self.gif_builder.set_background_color(255, 255, 255, 255)

        success, failed = 0, 0
        used_names: set = set()
        for i, group in enumerate(groups):
            try:
                group_id = i  # GroupManager uses integer index as ID
                safe_name = "".join(c for c in group.name if c.isalnum() or c in (' ', '-', '_')).strip() or f"group_{i}"
                base = safe_name
                n = 1
                while safe_name + ".gif" in used_names:
                    safe_name = f"{base}_{n}"; n += 1
                used_names.add(safe_name + ".gif")
                out_path = str(Path(export_dir) / (safe_name + ".gif"))
                self.gif_builder.build_gif_from_group(
                    group_id, self.group_manager, self.material_manager, out_path
                )
                success += 1
            except Exception as e:
                failed += 1
                print(f"Batch export error for group {i}: {e}")

        msg = f"Exported {success}/{len(groups)} group(s) to:\n{export_dir}"
        if failed:
            msg += f"\n({failed} failed — see console for details)"
        QMessageBox.information(self, "Batch Export Complete", msg)
        self._status(f"Batch exported {success} group(s)")

    # ──────────────────────────────────────────────────────────────
    # Spritesheet Export
    # ──────────────────────────────────────────────────────────────

    def export_spritesheet(self):
        """Export all frames of the current group as a single PNG spritesheet."""
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "No group selected!")
            return
        try:
            self.gif_builder.set_output_size(
                self.width_spinbox.value(), self.height_spinbox.value()
            )
            if self.transparent_bg_checkbox.isChecked():
                self.gif_builder.set_background_color(0, 0, 0, 0)
            else:
                self.gif_builder.set_background_color(255, 255, 255, 255)
            frames = self.gif_builder.get_preview_frames_for_group(
                self.current_group_id, self.group_manager, self.material_manager
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to render frames:\n{str(e)}")
            return

        if not frames:
            QMessageBox.warning(self, "Warning", "No frames in current group!")
            return

        # Ask how many columns
        n_cols, ok = QInputDialog.getInt(
            self, "Spritesheet Columns",
            f"Frames: {len(frames)}\nColumns per row:",
            value=min(len(frames), 8), min=1, max=len(frames)
        )
        if not ok:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Spritesheet", self.last_export_dir, "PNG Files (*.png)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"
        self.last_export_dir = str(Path(file_path).parent)

        try:
            frame_w = self.width_spinbox.value()
            frame_h = self.height_spinbox.value()
            n_rows = (len(frames) + n_cols - 1) // n_cols
            sheet = Image.new("RGBA", (frame_w * n_cols, frame_h * n_rows), (0, 0, 0, 0))
            for idx, (img, _) in enumerate(frames):
                col = idx % n_cols
                row = idx // n_cols
                frame_img = img.convert("RGBA").resize((frame_w, frame_h), Image.Resampling.LANCZOS)
                sheet.paste(frame_img, (col * frame_w, row * frame_h))
            sheet.save(file_path, "PNG")
            self._status(f"Spritesheet saved ({len(frames)} frames, {n_cols}×{n_rows})")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save spritesheet:\n{str(e)}")
