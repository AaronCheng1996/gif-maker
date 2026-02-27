from .utils import *
from .image_loader import ImageLoader, MaterialManager
from .sequence_editor import SequenceEditor, Frame
from .gif_builder import GifBuilder
from .layer_system import Layer, LayeredFrame, LayerCompositor
from .layered_sequence_editor import LayeredSequenceEditor
# New layer timeline module (renamed from multi_timeline)
from .layer_timeline import (
    LayerTimelineEditor, LayerTrack, LayerFrame,
    # Backward compatibility aliases (deprecated)
    MultiTimelineEditor, Timeline, TimelineFrame
)
from .template_manager import TemplateManager
from .batch_processor import BatchProcessor, BatchProcessingError
from .material_group import MaterialGroup
from .group_manager import GroupManager
from .composition_group import (
    CompositionGroup,
    FrameEntry,
    SubGroupEntry,
    LayerBlockEntry,
    FrameSlot,
    GroupSlot,
    Slot,
    Timeline,
    Entry,
    is_frame_entry,
    is_sub_group_entry,
    is_layer_block_entry,
    is_frame_slot,
    is_group_slot,
    # Serialization helpers
    slot_to_dict, slot_from_dict,
    entry_to_dict, entry_from_dict,
    group_to_dict, group_from_dict,
    max_material_index, remap_material_indices,
)

__all__ = [
    'ImageLoader',
    'MaterialManager',
    'SequenceEditor',
    'Frame',
    'GifBuilder',
    'Layer',
    'LayeredFrame',
    'LayerCompositor',
    'LayeredSequenceEditor',
    # New names
    'LayerTimelineEditor',
    'LayerTrack',
    'LayerFrame',
    # Deprecated aliases (for backward compatibility)
    'MultiTimelineEditor',
    'Timeline',
    'TimelineFrame',
    'TemplateManager',
    'BatchProcessor',
    'BatchProcessingError',
    'MaterialGroup',
    'GroupManager',
    'CompositionGroup',
    'FrameEntry',
    'SubGroupEntry',
    'LayerBlockEntry',
    'FrameSlot',
    'GroupSlot',
    'Slot',
    'Timeline',
    'Entry',
    'is_frame_entry',
    'is_sub_group_entry',
    'is_layer_block_entry',
    'is_frame_slot',
    'is_group_slot',
]

