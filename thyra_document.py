from typing import List, Tuple
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

from app.ui.vector_masks import BoundingBox, PolygonShape


@dataclass_json
@dataclass
class ThyraDocument:
    src_file_path: str = ""
    src_file_type: str = ""  # 'video' or 'image'

    boxes: List[Tuple[int, BoundingBox]] = field(
        default_factory=list,
        metadata=config(
            encoder=lambda boxes: [
                {"ts": ts, **box.to_dict()} for ts, box in boxes
            ],
            decoder=lambda boxes: [
                (box.get("ts", 0), BoundingBox.from_dict(box)) for box in boxes
            ]
        )
    )

    polygons: List[Tuple[int, PolygonShape]] = field(
        default_factory=list,
        metadata=config(
            encoder=lambda polys: [
                {"ts": ts, **poly.to_dict()} for ts, poly in polys
            ],
            decoder=lambda polys: [
                (poly.get("ts", 0), PolygonShape.from_dict(poly)) for poly in
                polys
            ]
        )
    )
