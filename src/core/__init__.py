from .utils import *
from .image_loader import ImageLoader, MaterialManager
from .gif_builder import GifBuilder
from .template_manager import TemplateManager
from .batch_processor import BatchProcessor, BatchProcessingError
from .group_manager import GroupManager
from .composition_group import (
    CompositionGroup,
    FrameEntry,
    SubGroupEntry,
    LayerBlockEntry,
    FrameSlot,
    GroupSlot,
    Slot,
    Entry,
    is_frame_entry,
    is_sub_group_entry,
    is_layer_block_entry,
    is_frame_slot,
    is_group_slot,
    slot_to_dict, slot_from_dict,
    entry_to_dict, entry_from_dict,
    group_to_dict, group_from_dict,
    max_material_index, remap_material_indices,
)

__all__ = [
    'ImageLoader',
    'MaterialManager',
    'GifBuilder',
    'TemplateManager',
    'BatchProcessor',
    'BatchProcessingError',
    'GroupManager',
    'CompositionGroup',
    'FrameEntry',
    'SubGroupEntry',
    'LayerBlockEntry',
    'FrameSlot',
    'GroupSlot',
    'Slot',
    'Entry',
    'is_frame_entry',
    'is_sub_group_entry',
    'is_layer_block_entry',
    'is_frame_slot',
    'is_group_slot',
]

