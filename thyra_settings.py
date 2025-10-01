from typing import List, Tuple
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

from app.ui.vector_masks import BoundingBox, PolygonShape


@dataclass_json
@dataclass
class ThyraSettings:
    most_recent_document_path: str = ""