from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
                              QMessageBox, QListWidget, QListWidgetItem, QGroupBox,
                              QComboBox, QInputDialog, QLabel)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image

from ..i18n import tr
from ..core import FrameEntry, CompositionGroup, SubGroupEntry
from ..widgets.canvas_editor import MATERIAL_INDEX_MIME_TYPE


class MaterialListWidget(QListWidget):
    """QListWidget that exposes the dragged item's material index as custom MIME
    data, so drop targets (e.g. the Canvas tab) know which material was dropped."""

    def mimeData(self, items):
        data = super().mimeData(items)
        if items:
            material_index = items[0].data(Qt.ItemDataRole.UserRole)
            if material_index is not None:
                data.setData(MATERIAL_INDEX_MIME_TYPE, str(material_index).encode("utf-8"))
        return data


class MaterialsPanelMixin:
    """Material library panel: loading, listing, exporting, and adding materials to groups."""

    def create_material_library_panel(self) -> QWidget:
        """Permanent left-side material library panel, always visible across all tool tabs."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel(tr("Material Library"))
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #e6eaf6; padding: 4px 0;")
        layout.addWidget(title)

        layout.addWidget(self.create_materials_tab())

        panel.setLayout(layout)
        return panel

    def create_materials_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        load_group = QGroupBox(tr("Load Materials"))
        load_layout = QVBoxLayout()

        self.load_image_btn = QPushButton(tr("Load Image"))
        self.load_image_btn.clicked.connect(self.load_image_material)
        load_layout.addWidget(self.load_image_btn)

        self.load_gif_btn = QPushButton(tr("Load GIF (Extract Frames)"))
        self.load_gif_btn.clicked.connect(self.load_gif_material)
        load_layout.addWidget(self.load_gif_btn)

        self.load_multiple_btn = QPushButton(tr("Load Multiple Images"))
        self.load_multiple_btn.clicked.connect(self.load_multiple_materials)
        load_layout.addWidget(self.load_multiple_btn)

        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        lib_header_row = QHBoxLayout()
        list_label = QLabel(tr("Material Library"))
        list_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8a95b8;")
        lib_header_row.addWidget(list_label)
        lib_header_row.addStretch()
        self.material_view_btn = QPushButton(tr("⊞ Grid"))
        self.material_view_btn.setFixedSize(80, 26)
        self.material_view_btn.setToolTip("Switch between list and grid (icon) view")
        self.material_view_btn.setCheckable(True)
        self.material_view_btn.clicked.connect(self._toggle_material_view)
        lib_header_row.addWidget(self.material_view_btn)
        layout.addLayout(lib_header_row)

        self._material_icon_mode = False  # False = list, True = icon/grid

        # Sorting controls for materials
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel(tr("Sort:")))
        self.material_sort_combo = QComboBox()
        self.material_sort_combo.addItems([
            tr("Default"),
            tr("Name (A→Z)"),
            tr("Name (Z→A)"),
            tr("Width (Large→Small)"),
            tr("Height (Large→Small)"),
        ])
        self.material_sort_combo.currentIndexChanged.connect(self.refresh_materials_list)
        sort_row.addWidget(self.material_sort_combo)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self.materials_list = MaterialListWidget()
        self.materials_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.materials_list.setIconSize(QSize(64, 64))
        self.materials_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.materials_list.setDragEnabled(True)
        layout.addWidget(self.materials_list)

        material_actions = QHBoxLayout()

        self.remove_material_btn = QPushButton(tr("Remove Selected"))
        self.remove_material_btn.clicked.connect(self.remove_selected_material)
        material_actions.addWidget(self.remove_material_btn)

        self.clear_materials_btn2 = QPushButton(tr("Clear All"))
        self.clear_materials_btn2.clicked.connect(self.clear_materials)
        material_actions.addWidget(self.clear_materials_btn2)

        layout.addLayout(material_actions)

        # Group addition buttons
        group_add_layout = QVBoxLayout()
        group_add_layout.setSpacing(4)

        self.add_to_existing_group_btn = QPushButton(tr("➕ Add to Selected Group"))
        self.add_to_existing_group_btn.setToolTip("Add selected materials to the currently selected group")
        self.add_to_existing_group_btn.clicked.connect(self.add_materials_to_existing_group)
        group_add_layout.addWidget(self.add_to_existing_group_btn)

        self.add_as_single_group_btn = QPushButton(tr("📦 Add as New Group"))
        self.add_as_single_group_btn.setToolTip("Create a standalone new group from selected materials (not nested into any group)")
        self.add_as_single_group_btn.clicked.connect(self.add_materials_as_standalone_group)
        group_add_layout.addWidget(self.add_as_single_group_btn)

        self.add_to_group_as_subgroup_btn = QPushButton(tr("📦➕ Add to Selected Group as New Group"))
        self.add_to_group_as_subgroup_btn.setToolTip("Create a new group from selected materials and nest it into the currently selected group")
        self.add_to_group_as_subgroup_btn.clicked.connect(self.add_materials_as_single_group)
        group_add_layout.addWidget(self.add_to_group_as_subgroup_btn)

        self.add_each_as_group_btn = QPushButton(tr("📦📦 Add Each as Group"))
        self.add_each_as_group_btn.setToolTip("Create a separate group for each selected material and add to timeline")
        self.add_each_as_group_btn.clicked.connect(self.add_materials_as_separate_groups)
        group_add_layout.addWidget(self.add_each_as_group_btn)

        layout.addLayout(group_add_layout)

        # Export materials section
        export_group = QGroupBox(tr("Export Materials"))
        export_layout = QVBoxLayout()

        self.export_selected_btn = QPushButton(tr("Export Selected Images"))
        self.export_selected_btn.clicked.connect(self.export_selected_materials)
        export_layout.addWidget(self.export_selected_btn)

        self.export_all_btn = QPushButton(tr("Export All Images"))
        self.export_all_btn.clicked.connect(self.export_all_materials)
        export_layout.addWidget(self.export_all_btn)

        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        widget.setLayout(layout)
        return widget

    def _get_selected_material_indices(self) -> List[int]:
        """Return list of selected material indices from the materials list (for Add Frame)."""
        indices = []
        for item in self.materials_list.selectedItems():
            row = self.materials_list.row(item)
            if 0 <= row < len(self.material_manager):
                indices.append(row)
        return sorted(indices)

    def load_image_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            self.last_image_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )

        if file_path:
            try:
                self.last_image_dir = str(Path(file_path).parent)
                self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                self._add_to_recent_files(file_path)
                self._status(f"Loaded: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")

    def load_gif_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GIF",
            self.last_gif_dir,
            "GIF Files (*.gif)"
        )

        if file_path:
            try:
                self.last_gif_dir = str(Path(file_path).parent)
                self.material_manager.load_from_gif(file_path)
                self.refresh_materials_list()
                self._add_to_recent_files(file_path)
                self._status(f"GIF loaded — {len(self.material_manager)} frames total")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load GIF:\n{str(e)}")

    def load_multiple_materials(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            self.last_image_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_paths:
            try:
                self.last_image_dir = str(Path(file_paths[0]).parent)
                for file_path in file_paths:
                    self.material_manager.load_from_image(file_path)
                    self._add_to_recent_files(file_path)
                self.refresh_materials_list()
                self._status(f"Loaded {len(file_paths)} image(s)")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load images:\n{str(e)}")

    def on_tiles_created(self, tiles):
        """
        Handle tiles created from tile splitter
        tiles: List[Tuple[Image, str]] - (tile_image, source_filename)
        """
        try:
            # Group tiles by source filename to number them per source
            from collections import defaultdict
            tile_counters = defaultdict(int)

            for tile_img, source_filename in tiles:
                tile_counters[source_filename] += 1
                tile_number = tile_counters[source_filename]
                # Create name like: "filename_tile_1", "filename_tile_2", etc.
                tile_name = f"{source_filename}_tile_{tile_number}"
                self.material_manager.add_material(tile_img, tile_name)

            self.refresh_materials_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add tiles:\n{str(e)}")

    def _toggle_material_view(self, checked: bool):
        self._material_icon_mode = checked
        self.material_view_btn.setText(tr("☰ List") if checked else tr("⊞ Grid"))
        self.refresh_materials_list()

    def refresh_materials_list(self):
        self.materials_list.clear()
        self._update_status_labels()

        # Determine sort order
        indices = list(range(len(self.material_manager)))
        sort_mode = getattr(self, 'material_sort_combo', None).currentText() if hasattr(self, 'material_sort_combo') else "Default"

        def get_name(idx):
            m = self.material_manager.get_material(idx)
            return m[1] if m else ""

        def get_size(idx):
            m = self.material_manager.get_material(idx)
            if not m:
                return (0, 0)
            img = m[0]
            return (img.width, img.height)

        if sort_mode == "Name (A→Z)":
            indices.sort(key=lambda i: get_name(i).lower())
        elif sort_mode == "Name (Z→A)":
            indices.sort(key=lambda i: get_name(i).lower(), reverse=True)
        elif sort_mode == "Width (Large→Small)":
            indices.sort(key=lambda i: get_size(i)[0], reverse=True)
        elif sort_mode == "Height (Large→Small)":
            indices.sort(key=lambda i: get_size(i)[1], reverse=True)
        # else Default keeps original order

        icon_mode = getattr(self, '_material_icon_mode', False)
        if icon_mode:
            self.materials_list.setViewMode(QListWidget.ViewMode.IconMode)
            self.materials_list.setIconSize(QSize(80, 80))
            self.materials_list.setGridSize(QSize(100, 110))
            self.materials_list.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.materials_list.setWordWrap(True)
            self.materials_list.setSpacing(4)
        else:
            self.materials_list.setViewMode(QListWidget.ViewMode.ListMode)
            self.materials_list.setIconSize(QSize(64, 64))
            self.materials_list.setGridSize(QSize())
            self.materials_list.setSpacing(0)

        for i in indices:
            mat = self.material_manager.get_material(i)
            if not mat:
                continue
            img, name = mat
            if icon_mode:
                thumbnail = self.create_thumbnail(img, 80, 80)
                icon = QIcon(thumbnail)
                short_name = name if len(name) <= 12 else name[:11] + "…"
                item = QListWidgetItem(icon, short_name)
                item.setToolTip(f"[{i}] {name}\n{img.width}×{img.height}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                item.setSizeHint(QSize(96, 106))
            else:
                thumbnail = self.create_thumbnail(img, 64, 64)
                icon = QIcon(thumbnail)
                item = QListWidgetItem(icon, f"[{i}] {name} ({img.width}x{img.height})")
                item.setSizeHint(QSize(200, 70))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.materials_list.addItem(item)

    def create_thumbnail(self, pil_image, width, height):
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)

        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')

        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def remove_selected_material(self):
        # Map selected view rows to underlying material indices
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
        selected_rows = sorted(selected_rows, reverse=True)
        if selected_rows:
            for row in selected_rows:
                self.material_manager.remove_material(row)
            self.refresh_materials_list()
        else:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")

    def add_materials_to_existing_group(self):
        """Add selected materials as FrameEntry to an existing group (group-led model)."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        groups = self.group_manager.get_all_groups()
        if not groups:
            QMessageBox.information(self, "Info", "Create a group first (e.g. Add as New Group).")
            return
        names = [g.name for g in groups]
        item, ok = QInputDialog.getItem(self, "Add to Group", "Select group to add materials to:", names, 0, False)
        if not ok:
            return
        idx = names.index(item)
        group = self.group_manager.get_group(idx)
        if not group:
            return
        original = len(group.entries)
        for m in material_indices:
            group.entries.append(FrameEntry(material_index=m, x=0, y=0))
        self.group_manager.update_group(idx, group)
        self.refresh_timeline()
        self.update_preview()
        self._status(f"Added {len(material_indices)} frame(s) to '{group.name}' ({len(group.entries)} entries total)")

    def add_materials_as_standalone_group(self):
        """Create a new CompositionGroup from selected materials as a top-level group (not nested)."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        name, ok = QInputDialog.getText(self, "New Group", "Group name:", text=f"Group_{len(material_indices)}")
        if not ok:
            return
        comp_group = CompositionGroup(
            name=name or f"Group_{len(material_indices)}",
            entries=[FrameEntry(material_index=m, x=0, y=0) for m in material_indices],
            default_duration_ms=100,
        )
        self.group_manager.add_group(comp_group)
        self.refresh_timeline()
        self.update_preview()
        self._status(f"Created standalone group '{comp_group.name}'")

    def add_materials_as_single_group(self):
        """Create a new CompositionGroup from selected materials and nest it into the current group."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        name, ok = QInputDialog.getText(self, "New Group", "Group name:", text=f"Group_{len(material_indices)}")
        if not ok:
            return
        comp_group = CompositionGroup(
            name=name or f"Group_{len(material_indices)}",
            entries=[FrameEntry(material_index=m, x=0, y=0) for m in material_indices],
            default_duration_ms=100,
        )
        group_idx = self.group_manager.add_group(comp_group)
        if self.current_group_id is not None:
            current = self.group_manager.get_group(self.current_group_id)
            if current:
                current.entries.append(SubGroupEntry(group_id=group_idx, loop_count=1))
                self.group_manager.update_group(self.current_group_id, current)
        self.refresh_timeline()
        self.update_preview()
        self._status(f"Created group '{comp_group.name}' and nested into current group")

    def add_materials_as_separate_groups(self):
        """Create one CompositionGroup per selected material and add each as SubGroupEntry to current group."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "Select a group in the Composition panel first.")
            return
        current = self.group_manager.get_group(self.current_group_id)
        if not current:
            return
        for mat_idx in material_indices:
            mat_name = f"Material_{mat_idx}"
            mat = self.material_manager.get_material(mat_idx)
            if mat:
                _, mat_name = mat
            comp_group = CompositionGroup(
                name=mat_name,
                entries=[FrameEntry(material_index=mat_idx, x=0, y=0)],
                default_duration_ms=100,
            )
            group_idx = self.group_manager.add_group(comp_group)
            current.entries.append(SubGroupEntry(group_id=group_idx, loop_count=1))
        self.group_manager.update_group(self.current_group_id, current)
        self.refresh_timeline()
        self.update_preview()
        self._status(f"Created {len(material_indices)} group(s) and added to timeline")

    def clear_materials(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Are you sure you want to clear all materials?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.material_manager.clear()
            self.refresh_materials_list()

    def export_selected_materials(self):
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one material to export!")
            return

        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            self.last_export_dir
        )

        if not export_dir:
            return

        try:
            # Remember the directory
            self.last_export_dir = export_dir

            exported_count = 0
            used_names = set()  # Track used filenames to avoid duplicates

            for row in selected_rows:
                if row < len(self.material_manager):
                    material = self.material_manager.get_material(row)
                    if material:
                        img, name = material
                        # Clean filename (remove invalid characters)
                        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        if not safe_name:
                            safe_name = f"material_{row}"

                        # Ensure unique filename
                        base_name = safe_name
                        counter = 1
                        final_name = base_name

                        while f"{final_name}.png" in used_names:
                            final_name = f"{base_name}_{counter}"
                            counter += 1

                        used_names.add(f"{final_name}.png")

                        # Export as PNG
                        export_path = f"{export_dir}/{final_name}.png"
                        img.save(export_path, "PNG")
                        exported_count += 1

            QMessageBox.information(self, "Success",
                f"Successfully exported {exported_count} images to:\n{export_dir}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export images:\n{str(e)}")

    def export_all_materials(self):
        if len(self.material_manager) == 0:
            QMessageBox.warning(self, "Warning", "No materials to export!")
            return

        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            self.last_export_dir
        )

        if not export_dir:
            return

        try:
            # Remember the directory
            self.last_export_dir = export_dir

            exported_count = 0
            used_names = set()  # Track used filenames to avoid duplicates

            for i in range(len(self.material_manager)):
                material = self.material_manager.get_material(i)
                if material:
                    img, name = material
                    # Clean filename (remove invalid characters)
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    if not safe_name:
                        safe_name = f"material_{i}"

                    # Ensure unique filename
                    base_name = safe_name
                    counter = 1
                    final_name = base_name

                    while f"{final_name}.png" in used_names:
                        final_name = f"{base_name}_{counter}"
                        counter += 1

                    used_names.add(f"{final_name}.png")

                    # Export as PNG
                    export_path = f"{export_dir}/{final_name}.png"
                    img.save(export_path, "PNG")
                    exported_count += 1

            QMessageBox.information(self, "Success",
                f"Successfully exported {exported_count} images to:\n{export_dir}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export images:\n{str(e)}")
