from typing import List, Tuple, Union
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

from app.ui.vector_masks import BoundingBox, PolygonShape


@dataclass_json
@dataclass
class ThyraDocument:
    src_file_path: str = ""
    src_file_type: str = ""  # 'video' or 'image'

    boxes: List[BoundingBox] = field(
        default_factory=list,
        metadata=config(
            encoder=lambda boxes: [
                box.to_dict() for box in boxes
            ],
            decoder=lambda boxes: [
                BoundingBox.from_dict(box) for box in boxes
            ]
        )
    )

    polygons: List[PolygonShape] = field(
        default_factory=list,
        metadata=config(
            encoder=lambda polys: [
                poly.to_dict() for poly in polys
            ],
            decoder=lambda polys: [
                PolygonShape.from_dict(poly) for poly in
                polys
            ]
        )
    )

    def __post_init__(self):
        self.action_stack: List[Union[BoundingBox, PolygonShape]] = []

    def undo(self):
        latest = []
        self.boxes.sort(key=lambda x: x.ts)
        self.polygons.sort(key=lambda x: x.ts)
        if self.boxes:
            latest.append(self.boxes[-1])
        if self.polygons:
            latest.append(self.polygons[-1])
        if not latest:
            return None

        latest.sort(key=lambda x: x.ts)
        item = latest[-1]
        if isinstance(item, BoundingBox):
            item = self.boxes.pop()
        elif isinstance(item, PolygonShape):
            item = self.polygons.pop()
        self.action_stack.append(item)

    def redo(self)->bool:
        if not self.action_stack:
            return False
        item = self.action_stack.pop()
        shape = item
        if isinstance(shape, BoundingBox):
            self.boxes.append(shape)
        elif isinstance(shape, PolygonShape):
            self.polygons.append(shape)

    def clear(self):
        self.boxes.clear()
        self.polygons.clear()


