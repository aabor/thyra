from dataclasses import dataclass, field
from typing import List, Tuple
from dataclasses_json import dataclass_json, config


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

    def normalized(self, canvas_w: float, canvas_h: float) -> dict:
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError("Canvas size must be positive")
        return {
            "id": self.id,
            "x": self.x / canvas_w,
            "y": self.y / canvas_h,
            "w": self.w / canvas_w,
            "h": self.h / canvas_h,
        }

    @classmethod
    def denormalized(cls, data: dict, canvas_w: float, canvas_h: float):
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError("Canvas size must be positive")
        return cls(
            x=data["x"] * canvas_w,
            y=data["y"] * canvas_h,
            w=data["w"] * canvas_w,
            h=data["h"] * canvas_h,
            id=data["id"],
        )


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

    def normalized(self, canvas_w: float, canvas_h: float) -> dict:
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError("Canvas size must be positive")
        norm_points = [(x / canvas_w, y / canvas_h) for (x, y) in self.points]
        return {
            "id": self.id,
            "points": norm_points,
        }

    @classmethod
    def denormalized(cls, data: dict, canvas_w: float, canvas_h: float):
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError("Canvas size must be positive")
        abs_points = [(x * canvas_w, y * canvas_h) for (x, y) in data["points"]]
        return cls(points=abs_points, id=data["id"])
