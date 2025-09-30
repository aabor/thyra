from typing import List, Tuple
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from app.ui.vector_masks import BoundingBox, PolygonShape


@dataclass_json
@dataclass
class ThyraSettings:
    most_recent_document_path: str = ""


@dataclass_json
@dataclass
class ThyraDocument:
    src_file_path: str = ""
    src_file_type: str = ""  # 'video' or 'image'
    boxes: List[Tuple[int, BoundingBox]] = field(default_factory=list)
    polygons: List[Tuple[int, PolygonShape]] = field(default_factory=list)
