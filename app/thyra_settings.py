from typing import List, Tuple
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

from app.ui.polygone_shape import PolygonShape
from app.ui.bounding_box import BoundingBox


@dataclass_json
@dataclass
class ThyraSettings:
    most_recent_document_path: str = ""