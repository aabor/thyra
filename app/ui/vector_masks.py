from dataclasses import dataclass
from typing import List, Tuple


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


@dataclass
class PolygonShape:
    points: List[Tuple[float, float]]
    id: str

    def to_coco_segmentation(self):
        flattened = []
        for x, y in self.points:
            flattened.extend([x, y])
        return [flattened]
