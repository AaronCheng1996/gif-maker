from collections import Counter
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QGroupBox, QListWidget, QSpinBox, QCheckBox, QComboBox,
                              QColorDialog, QMessageBox, QTabWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

from PIL import Image

from ..i18n import tr
from ..core import FrameEntry, CompositionGroup
from ..widgets import GroupCompositionWidget, PreviewWidget, CanvasEditorWidget


class ComposerPanelMixin:
    """Composer middle/right panels: group tree host, preview, template UI shell,
    output settings, chroma key, and auto-layout alignment."""

    def create_middle_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        title = QLabel(tr("Composition (Groups)"))
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #e6eaf6; padding: 4px 0;")
        layout.addWidget(title)
        self.group_composition_widget = GroupCompositionWidget()
        self.group_composition_widget.set_group_manager(self.group_manager)
        self.group_composition_widget.set_material_manager(self.material_manager)
        self.group_composition_widget.set_get_selected_material_indices(self._get_selected_material_indices)
        self.group_composition_widget.current_group_changed.connect(self._on_current_group_changed)
        self.group_composition_widget.entries_changed.connect(self._on_group_entries_changed)

        self.canvas_editor = CanvasEditorWidget()
        self.canvas_editor.entry_selected.connect(self._on_canvas_entry_selected)
        self.canvas_editor.entries_edited.connect(self._on_canvas_entries_edited)
        self.canvas_editor.material_dropped.connect(self._on_canvas_material_dropped)
        self.group_composition_widget.frame_entry_selected.connect(self._on_tree_entry_selected)

        self.middle_view_tabs = QTabWidget()
        self.middle_view_tabs.addTab(self.group_composition_widget, tr("🌳 Tree"))
        self.middle_view_tabs.addTab(self.canvas_editor, tr("🖼 Canvas"))
        layout.addWidget(self.middle_view_tabs, stretch=1)
        panel.setLayout(layout)

        self._refresh_canvas()
        return panel

    def _on_current_group_changed(self, group_id: int):
        self.current_group_id = group_id
        if getattr(self, 'auto_size_checkbox', None) and self.auto_size_checkbox.isChecked():
            self.auto_fit_output_size()
        self.update_preview()
        self._update_status_labels()
        self._refresh_canvas()

    def _on_auto_size_toggled(self, state: int):
        """Enable/disable size spinboxes based on Auto checkbox; auto-fit immediately when enabled."""
        manual = (state == 0)
        self.width_spinbox.setEnabled(manual)
        self.height_spinbox.setEnabled(manual)
        if not manual:
            self.auto_fit_output_size()

    def _on_group_entries_changed(self):
        self.update_preview()
        self._refresh_canvas()
        if not self._undo_in_progress:
            self._undo_debounce.start(300)

    def _on_canvas_entries_edited(self):
        """A canvas drag finished and changed an entry's x/y offset."""
        self.refresh_timeline()
        self.update_preview()
        self._refresh_canvas()
        if not self._undo_in_progress:
            self._undo_debounce.start(300)

    def _on_canvas_entry_selected(self, entry_idx: int):
        """Canvas selection -> mirror onto the tree (Tree <-> Canvas sync)."""
        self.group_composition_widget.set_selected_entry(
            self.current_group_id, entry_idx if entry_idx >= 0 else None
        )

    def _on_tree_entry_selected(self, parent_gid: int, entry_idx: int):
        """Tree selection -> mirror onto the canvas, only when it's for the group Canvas shows."""
        if parent_gid == self.current_group_id:
            self.canvas_editor.select_entry(entry_idx)
        else:
            self.canvas_editor.select_entry(None)

    def _on_canvas_material_dropped(self, material_index: int, x: float, y: float):
        """A material was dragged from the library and dropped onto the canvas:
        add it as a new FrameEntry, centered on the drop point."""
        group = self._get_current_group()
        if group is None:
            return
        mat = self.material_manager.get_material(material_index)
        if mat is None:
            return
        img, _name = mat
        drop_x = int(round(x - img.width / 2))
        drop_y = int(round(y - img.height / 2))
        group.entries.append(FrameEntry(material_index=material_index, x=drop_x, y=drop_y))
        self.group_manager.update_group(self.current_group_id, group)
        self.refresh_timeline()
        self.update_preview()
        self._refresh_canvas()
        if not self._undo_in_progress:
            self._undo_debounce.start(300)
        self._status(f"Added frame from material library drop ({drop_x}, {drop_y})")

    def _refresh_canvas(self):
        """Sync the Canvas tab with the current group's entries and output size."""
        if not hasattr(self, 'canvas_editor'):
            return
        if hasattr(self, 'width_spinbox') and hasattr(self, 'height_spinbox'):
            self.canvas_editor.set_output_size(self.width_spinbox.value(), self.height_spinbox.value())
        group = self._get_current_group()
        entries = group.entries if group else []
        self.canvas_editor.set_entries(entries, self.material_manager)

    def create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)

        # Preview background color button (compact toolbar)
        preview_controls = QHBoxLayout()
        self.preview_bg_btn = QPushButton(tr("🎨 BG"))
        self.preview_bg_btn.setToolTip("Set preview background color (does not affect export)")
        self.preview_bg_btn.setMaximumWidth(60)
        self.preview_bg_btn.clicked.connect(self.on_choose_preview_bg)
        preview_controls.addWidget(self.preview_bg_btn)
        preview_controls.addStretch()
        self.info_label = QLabel("Frame: 0/0")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_controls.addWidget(self.info_label)
        layout.addLayout(preview_controls)

        # Preview (centered horizontally)
        preview_container = QHBoxLayout()
        preview_container.addStretch()  # Add stretch before preview
        self.preview = PreviewWidget()
        self.preview.frame_info_changed.connect(self.on_preview_frame_info_changed)
        self.preview.preview_clicked.connect(self.on_preview_clicked)
        self.preview.setMaximumHeight(400)  # Limit max height (accounts for control buttons)
        preview_container.addWidget(self.preview)  # Add preview widget
        preview_container.addStretch()  # Add stretch after preview
        layout.addLayout(preview_container)

        # Template management section (more space)
        template_group = QGroupBox(tr("Template Manager"))
        template_layout = QVBoxLayout()
        template_layout.setSpacing(3)

        # Template list (larger for easier management)
        self.template_list = QListWidget()
        self.template_list.setMinimumHeight(120)  # More visible space
        self.template_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        template_layout.addWidget(self.template_list)

        # Template action buttons (2 rows)
        template_row1 = QHBoxLayout()
        self.save_template_btn = QPushButton(tr("💾 Save"))
        self.save_template_btn.clicked.connect(self.quick_save_template)
        self.save_template_btn.setToolTip("Save current timeline as template")
        template_row1.addWidget(self.save_template_btn)

        self.apply_template_btn = QPushButton(tr("✓ Apply"))
        self.apply_template_btn.clicked.connect(self.quick_apply_template)
        self.apply_template_btn.setToolTip("Apply selected template to current materials")
        template_row1.addWidget(self.apply_template_btn)
        template_layout.addLayout(template_row1)

        template_row2 = QHBoxLayout()
        self.import_template_btn = QPushButton(tr("📂 Import"))
        self.import_template_btn.clicked.connect(self.quick_import_template)
        self.import_template_btn.setToolTip("Import template from file")
        template_row2.addWidget(self.import_template_btn)

        self.export_template_btn = QPushButton(tr("💾 Export"))
        self.export_template_btn.clicked.connect(self.quick_export_template)
        self.export_template_btn.setToolTip("Export selected template to file")
        template_row2.addWidget(self.export_template_btn)

        self.remove_template_btn = QPushButton(tr("🗑 Remove"))
        self.remove_template_btn.clicked.connect(self.remove_template)
        self.remove_template_btn.setToolTip("Remove selected template from list")
        template_row2.addWidget(self.remove_template_btn)
        template_layout.addLayout(template_row2)

        template_group.setLayout(template_layout)
        layout.addWidget(template_group, stretch=1)  # Allow template section to expand

        # Compact settings section
        settings_group = QGroupBox(tr("Settings"))
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(3)

        # Size (more compact) — with Auto checkbox
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel(tr("Size:")))
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setMinimum(1)
        self.width_spinbox.setMaximum(4096)
        self.width_spinbox.setValue(400)
        self.width_spinbox.valueChanged.connect(self._refresh_canvas)
        size_layout.addWidget(self.width_spinbox)
        size_layout.addWidget(QLabel("×"))
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(1)
        self.height_spinbox.setMaximum(4096)
        self.height_spinbox.setValue(400)
        self.height_spinbox.valueChanged.connect(self._refresh_canvas)
        size_layout.addWidget(self.height_spinbox)
        self.auto_size_checkbox = QCheckBox(tr("Auto"))
        self.auto_size_checkbox.setToolTip(
            "Auto-fit output size to materials whenever the selected group changes"
        )
        self.auto_size_checkbox.stateChanged.connect(self._on_auto_size_toggled)
        size_layout.addWidget(self.auto_size_checkbox)
        size_layout.addStretch()
        settings_layout.addLayout(size_layout)

        # Loop (compact)
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel(tr("Loop:")))
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setMinimum(0)
        self.loop_spinbox.setMaximum(1000)
        self.loop_spinbox.setValue(0)
        self.loop_spinbox.setSpecialValueText("∞")
        loop_layout.addWidget(self.loop_spinbox)
        loop_layout.addStretch()
        settings_layout.addLayout(loop_layout)

        # Transparent BG
        self.transparent_bg_checkbox = QCheckBox(tr("Transparent BG"))
        self.transparent_bg_checkbox.stateChanged.connect(self.on_transparent_bg_changed)
        settings_layout.addWidget(self.transparent_bg_checkbox)

        # Color palette selection
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel(tr("Colors:")))
        self.color_palette_combo = QComboBox()
        self.color_palette_combo.addItems(["256", "128", "64", "32", "16"])
        self.color_palette_combo.setCurrentText("256")
        self.color_palette_combo.currentTextChanged.connect(self.on_color_palette_changed)
        color_layout.addWidget(self.color_palette_combo)
        color_layout.addStretch()
        settings_layout.addLayout(color_layout)

        # Chroma key (green screen) selection
        chroma_layout = QHBoxLayout()
        chroma_layout.addWidget(QLabel(tr("Chroma Key:")))
        self.chroma_key_combo = QComboBox()
        self.chroma_key_combo.addItem(tr("None (Disabled)"))
        self.chroma_key_combo.setToolTip("Select a color to make transparent (green screen effect)")
        self.chroma_key_combo.currentIndexChanged.connect(self.on_chroma_key_changed)
        self.chroma_key_combo.setMinimumWidth(150)
        chroma_layout.addWidget(self.chroma_key_combo)

        self.analyze_colors_btn = QPushButton("🔍")
        self.analyze_colors_btn.setMaximumWidth(30)
        self.analyze_colors_btn.setToolTip("Analyze colors from first frame")
        self.analyze_colors_btn.clicked.connect(self.analyze_first_frame_colors)
        chroma_layout.addWidget(self.analyze_colors_btn)

        self.show_more_colors_btn = QPushButton("+10")
        self.show_more_colors_btn.setMaximumWidth(40)
        self.show_more_colors_btn.setToolTip("Show 10 more color options")
        self.show_more_colors_btn.clicked.connect(self.show_more_colors)
        self.show_more_colors_btn.setEnabled(False)
        chroma_layout.addWidget(self.show_more_colors_btn)

        chroma_layout.addStretch()
        settings_layout.addLayout(chroma_layout)


        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group, stretch=0)

        # Auto Layout section
        auto_layout_group = QGroupBox(tr("Auto Layout"))
        auto_layout_layout = QVBoxLayout()
        auto_layout_layout.setSpacing(3)

        # Auto fit size button
        self.auto_fit_size_btn = QPushButton(tr("🔧 Auto Fit Size"))
        self.auto_fit_size_btn.clicked.connect(self.auto_fit_output_size)
        self.auto_fit_size_btn.setToolTip("Automatically adjust output size to fit all materials")
        auto_layout_layout.addWidget(self.auto_fit_size_btn)

        # Horizontal alignment buttons
        h_align_label = QLabel(tr("Horizontal:"))
        h_align_label.setStyleSheet("font-size: 10px; color: #8a95b8;")
        auto_layout_layout.addWidget(h_align_label)

        h_align_layout = QHBoxLayout()
        self.align_left_btn = QPushButton(tr("⬅ Left"))
        self.align_left_btn.clicked.connect(self.align_all_left)
        self.align_left_btn.setToolTip("Align all materials to the left")
        h_align_layout.addWidget(self.align_left_btn)

        self.align_center_h_btn = QPushButton(tr("↔ Center"))
        self.align_center_h_btn.clicked.connect(self.align_all_center_horizontal)
        self.align_center_h_btn.setToolTip("Center all materials horizontally")
        h_align_layout.addWidget(self.align_center_h_btn)

        self.align_right_btn = QPushButton(tr("➡ Right"))
        self.align_right_btn.clicked.connect(self.align_all_right)
        self.align_right_btn.setToolTip("Align all materials to the right")
        h_align_layout.addWidget(self.align_right_btn)

        auto_layout_layout.addLayout(h_align_layout)

        v_align_label = QLabel(tr("Vertical:"))
        v_align_label.setStyleSheet("font-size: 10px; color: #8a95b8;")
        auto_layout_layout.addWidget(v_align_label)

        v_align_layout = QHBoxLayout()
        self.align_top_btn = QPushButton(tr("⬆ Top"))
        self.align_top_btn.clicked.connect(self.align_all_top)
        self.align_top_btn.setToolTip("Align all materials to the top")
        v_align_layout.addWidget(self.align_top_btn)

        self.align_middle_btn = QPushButton(tr("↕ Middle"))
        self.align_middle_btn.clicked.connect(self.align_all_middle_vertical)
        self.align_middle_btn.setToolTip("Center all materials vertically")
        v_align_layout.addWidget(self.align_middle_btn)

        self.align_bottom_btn = QPushButton(tr("⬇ Bottom"))
        self.align_bottom_btn.clicked.connect(self.align_all_bottom)
        self.align_bottom_btn.setToolTip("Align all materials to the bottom")
        v_align_layout.addWidget(self.align_bottom_btn)

        auto_layout_layout.addLayout(v_align_layout)

        auto_layout_group.setLayout(auto_layout_layout)
        layout.addWidget(auto_layout_group, stretch=0)

        # Action buttons (compact)
        self.update_preview_btn = QPushButton(tr("🔄 Preview"))
        self.update_preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(self.update_preview_btn)

        self.export_gif_btn = QPushButton(tr("💾 Export GIF"))
        self.export_gif_btn.clicked.connect(self.export_gif)
        self.export_gif_btn.setStyleSheet(
            "font-weight: 600; font-size: 13px; background-color: #1f6b40; "
            "color: #c8f0d8; border: 1px solid #2d8a54; border-radius: 4px; padding: 6px 14px;"
        )
        layout.addWidget(self.export_gif_btn)

        panel.setLayout(layout)
        return panel

    def _get_current_group(self) -> Optional["CompositionGroup"]:
        """Return the currently selected CompositionGroup, or None."""
        if self.current_group_id is None:
            return None
        return self.group_manager.get_group(self.current_group_id)

    def _align_current_group_entries(self, apply_fn) -> int:
        """Apply apply_fn(entry, mat_size) to FrameEntry items in the current group.

        If one or more items are selected on the Canvas tab, only those are
        aligned; otherwise every FrameEntry in the group is aligned (unchanged
        default behavior)."""
        group = self._get_current_group()
        if group is None:
            return 0
        selected_indices = None
        if hasattr(self, 'canvas_editor'):
            indices = self.canvas_editor.selected_entry_indices()
            if indices:
                selected_indices = set(indices)
        count = 0
        for idx, entry in enumerate(group.entries):
            if not isinstance(entry, FrameEntry):
                continue
            if selected_indices is not None and idx not in selected_indices:
                continue
            mat = self.material_manager.get_material(entry.material_index)
            if mat:
                apply_fn(entry, mat[0].size)
                count += 1
        return count

    def get_all_materials_max_size(self) -> Tuple[int, int]:
        """Return max (width, height) of all FrameEntry materials in the current group."""
        group = self._get_current_group()
        if group is None:
            return (0, 0)
        max_w = max_h = 0
        for entry in group.entries:
            if isinstance(entry, FrameEntry):
                mat = self.material_manager.get_material(entry.material_index)
                if mat:
                    w, h = mat[0].size
                    max_w = max(max_w, w)
                    max_h = max(max_h, h)
        return (max_w, max_h)

    def auto_fit_output_size(self):
        """Automatically adjust output size to fit all materials."""
        max_width, max_height = self.get_all_materials_max_size()

        if max_width == 0 or max_height == 0:
            QMessageBox.warning(
                self,
                "Warning",
                "No materials found in timeline!\nPlease add materials to frames first."
            )
            return

        self.width_spinbox.setValue(max_width)
        self.height_spinbox.setValue(max_height)
        self.update_preview()
        self._status(f"Output size set to {max_width} × {max_height}")

    def align_all_left(self):
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'x', 0))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Aligned {count} frame(s) to left")

    def align_all_center_horizontal(self):
        out_w = self.width_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'x', (out_w - sz[0]) // 2))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Centered {count} frame(s) horizontally")

    def align_all_right(self):
        out_w = self.width_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'x', out_w - sz[0]))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Aligned {count} frame(s) to right")

    def align_all_top(self):
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'y', 0))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Aligned {count} frame(s) to top")

    def align_all_middle_vertical(self):
        out_h = self.height_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'y', (out_h - sz[1]) // 2))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Centered {count} frame(s) vertically")

    def align_all_bottom(self):
        out_h = self.height_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'y', out_h - sz[1]))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview(); self._refresh_canvas()
        self._status(f"Aligned {count} frame(s) to bottom")

    def refresh_timeline(self):
        """Refresh group composition widget (group-led model)."""
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            self.group_composition_widget.refresh_groups_list()
            self.group_composition_widget.refresh_entries_list()
        return

    def on_preview_frame_info_changed(self, current: int, total: int, duration: int):
        """Handle preview frame info change"""
        if total > 0:
            self.info_label.setText(f"Frame: {current}/{total} | Duration: {duration}ms")
        else:
            self.info_label.setText("Frame: 0/0")

    def on_preview_clicked(self):
        """Handle preview image click - switch to preview page"""
        # 將當前的幀資料傳遞給預覽頁面
        if hasattr(self.preview, 'frames') and self.preview.frames:
            self.preview_page.set_frames(self.preview.frames)
            # Keep preview page background consistent
            try:
                self.preview_page.set_background_color(self.preview_bg_color)
            except Exception:
                pass
            self.show_preview_page()

    def on_choose_preview_bg(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.preview_bg_color = color.name()
            try:
                self.preview.set_background_color(color)
            except Exception:
                pass
            try:
                self.preview_page.set_background_color(color)
            except Exception:
                pass

    def on_transparent_bg_changed(self):
        """Handle transparent background checkbox change"""
        # Update preview with new transparency setting
        self.update_preview()

    def on_color_palette_changed(self):
        """Handle color palette selection change"""
        color_count = int(self.color_palette_combo.currentText())
        self.gif_builder.set_color_count(color_count)
        # Update preview with new color palette setting
        self.update_preview()

    def on_preview_mode_changed(self):
        """Kept for backwards compatibility; preview always shows full animation."""
        self.update_preview()

    def update_single_frame_preview(self):
        self.update_preview()

    def update_preview(self):
        """Update preview from the currently selected group (always full animation)."""
        if self.current_group_id is None:
            return
        if self.group_manager.get_group(self.current_group_id) is None:
            return
        try:
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
            frames = self.gif_builder.get_preview_frames_for_group(
                self.current_group_id,
                self.group_manager,
                self.material_manager,
            )
            self.preview.set_frames(frames)
        except Exception as e:
            print(f"ERROR in update_preview: {e}")
            import traceback
            traceback.print_exc()

    def create_color_icon(self, r: int, g: int, b: int, size: int = 16) -> QIcon:
        """Create a color preview icon"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.fillRect(0, 0, size, size, QColor(r, g, b))
        painter.end()

        return QIcon(pixmap)

    def analyze_first_frame_colors(self):
        """Analyze colors in the first frame of the current group and populate chroma key dropdown"""
        try:
            group = self._get_current_group()
            if group is None:
                QMessageBox.warning(self, "Warning", "No group selected!")
                return

            first_entry = next((e for e in group.entries if isinstance(e, FrameEntry)), None)
            if first_entry is None:
                QMessageBox.warning(self, "Warning", "No frames in the selected group to analyze!")
                return

            material = self.material_manager.get_material(first_entry.material_index)
            if not material:
                QMessageBox.warning(self, "Warning", "First frame material not found!")
                return

            img, _ = material

            # Convert to RGB for color analysis
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Sample colors (downsample for performance on large images)
            max_size = 200
            if img.width > max_size or img.height > max_size:
                # Create a thumbnail for analysis
                img_small = img.copy()
                img_small.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                img = img_small

            # Get all pixels
            pixels = list(img.getdata())
            total_pixels = len(pixels)

            # Count colors
            color_counts = Counter(pixels)

            # Get top colors (store all for "show more" functionality)
            top_colors = color_counts.most_common(100)  # Store up to 100

            # Store all colors with their percentages
            self.chroma_key_colors_all = []
            for color, count in top_colors:
                percentage = (count / total_pixels) * 100
                r, g, b = color
                # Create display name with color and percentage
                display_name = f"RGB({r},{g},{b}) - {percentage:.1f}%"
                self.chroma_key_colors_all.append((color, percentage, display_name))

            # Reset display count and update combo box
            self.chroma_key_display_count = 10
            self.update_chroma_key_combo()

            # Enable/disable show more button
            self.show_more_colors_btn.setEnabled(len(self.chroma_key_colors_all) > self.chroma_key_display_count)

            QMessageBox.information(
                self,
                "Analysis Complete",
                f"Analyzed {len(top_colors)} most common colors from first frame.\n"
                f"Showing top {min(10, len(top_colors))} colors.\n"
                f"Click '+10' to see more options."
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to analyze colors:\n{str(e)}")

    def update_chroma_key_combo(self):
        """Update chroma key combo box with current display count"""
        # Store current selection
        current_index = self.chroma_key_combo.currentIndex()

        self.chroma_key_combo.blockSignals(True)
        self.chroma_key_combo.clear()
        self.chroma_key_combo.addItem(tr("None (Disabled)"))

        # Add colors up to display count
        display_colors = self.chroma_key_colors_all[:self.chroma_key_display_count]
        for color_rgb, _, display_name in display_colors:
            r, g, b = color_rgb
            icon = self.create_color_icon(r, g, b)
            self.chroma_key_combo.addItem(icon, display_name)

        # Restore selection if valid
        if current_index < self.chroma_key_combo.count():
            self.chroma_key_combo.setCurrentIndex(current_index)
        else:
            self.chroma_key_combo.setCurrentIndex(0)

        self.chroma_key_combo.blockSignals(False)

    def show_more_colors(self):
        """Show 10 more color options"""
        if self.chroma_key_display_count < len(self.chroma_key_colors_all):
            self.chroma_key_display_count += 10
            self.update_chroma_key_combo()

            # Disable button if we've shown all colors
            if self.chroma_key_display_count >= len(self.chroma_key_colors_all):
                self.show_more_colors_btn.setEnabled(False)

    def on_chroma_key_changed(self):
        """Handle chroma key color selection change"""
        try:
            index = self.chroma_key_combo.currentIndex()
            if index == 0:
                self.gif_builder.clear_chroma_key()
            else:
                color_index = index - 1
                display_colors = self.chroma_key_colors_all[:self.chroma_key_display_count]
                if 0 <= color_index < len(display_colors):
                    color_rgb, _, _ = display_colors[color_index]
                    r, g, b = color_rgb
                    self.gif_builder.set_chroma_key(r, g, b, threshold=30)
            self.update_preview()
        except Exception as e:
            print(f"Error applying chroma key: {e}")
            import traceback
            traceback.print_exc()
