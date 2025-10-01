from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF
from dataclasses_json import dataclass_json

from app.computational_geometry.coordinates_convertion import \
    image_to_widget_coords


@dataclass_json
@dataclass
class BoundingBox:
    x: float
    y: float
    w: float
    h: float
    id: str
    ts: int  # timestamp

    def draw(self, painter: QPainter,
             img_w: int, img_h: int, widget_w: int, widget_h: int,
             rect: QRectF, pen: QPen):
        # coordinates are normalized in [0..1]
        x_abs = self.x * img_w
        y_abs = self.y * img_h
        w_abs = self.w * img_w
        h_abs = self.h * img_h
        p1 = image_to_widget_coords(
            x_abs, y_abs,
            img_w, img_h, widget_w, widget_h, rect)
        p2 = image_to_widget_coords(
            x_abs + w_abs, y_abs + h_abs,
            img_w, img_h, widget_w, widget_h, rect)
        draw_rect = QRectF(p1, p2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(draw_rect)

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
            "ts": self.ts,
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
            ts=data["ts"]
        )


@dataclass_json
@dataclass
class PolygonShape:
    points: List[Tuple[float, float]]
    id: str
    ts: int  # timestamp

    def draw(self, painter: QPainter,
             img_w: int, img_h: int, widget_w: int, widget_h: int,
             rect: QRectF, pen: QPen):
        pts = [image_to_widget_coords(
            x * img_w, y * img_h,
            img_w, img_h, widget_w, widget_h, rect)
            for x, y in self.points]
        if len(pts) >= 3:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF(pts))

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
            "ts": self.ts,
            "id": self.id,
            "points": norm_points,
        }

    @classmethod
    def denormalized(cls, data: dict, canvas_w: float, canvas_h: float):
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError("Canvas size must be positive")
        abs_points = [(x * canvas_w, y * canvas_h) for (x, y) in data["points"]]
        return cls(points=abs_points, id=data["id"], ts=data["ts"])
