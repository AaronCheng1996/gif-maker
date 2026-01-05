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
]

