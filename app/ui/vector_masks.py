from dataclasses import dataclass
from typing import List, Tuple
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class BoundingBox:
    x: float
    y: float
    w: float
    h: float
    id: str

    def to_coco_bbox(self):
        return [self.x, self.y, self.w, self.h]

    def to_polygon(self):
        x, y, w, h = self.x, self.y, self.w, self.h
        return [x, y, x + w, y, x + w, y + h, x, y + h]


@dataclass_json
@dataclass
class PolygonShape:
    points: List[Tuple[float, float]]
    id: str

    def to_coco_segmentation(self):
        flattened = []
        for x, y in self.points:
            flattened.extend([x, y])
        return [flattened]
