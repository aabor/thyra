from dataclasses_json import dataclass_json
from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF, QColor

from app.computational_geometry.coordinates_convertion import \
    image_to_widget_coords
from app.ui.vector_masks import VectorMask, register_vector_mask_object


@register_vector_mask_object
@dataclass_json
@dataclass
class PolygonShape(VectorMask):
    points: List[Tuple[float, float]]
    id: str
    ts: int  # timestamp

    def __post_init__(self):
        self.selected = False

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

    def update(self, x_img_norm: float, y_img_norm: float):
        """Append new vertex if it is far enough from the last one."""
        last_x, last_y = self.points[-1]
        if abs(last_x - x_img_norm) > 0.002 or abs(last_y - y_img_norm) > 0.002:
            self.points.append((x_img_norm, y_img_norm))

    def move(self, dx: float, dy: float):
        """Move polygon in normalized coordinates, clamped inside [0,1]."""
        new_points = []
        for x, y in self.points:
            nx = min(max(x + dx, 0.0), 1.0)
            ny = min(max(y + dy, 0.0), 1.0)
            new_points.append((nx, ny))
        self.points = new_points

    def contains(self, nx: float, ny: float) -> bool:
        """Ray casting point-in-polygon check in normalized coords."""
        inside = False
        pts = self.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > ny) != (yj > ny)) and \
                (nx < (xj - xi) * (ny - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def draw_points(self, painter, img_w, img_h, widget_w, widget_h, rect,
                    color=QColor(180, 180, 180)):
        """Draw small grey points for polygon vertices."""
        pen = QPen(color, 2)
        painter.setPen(pen)
        for nx, ny in self.points:
            px = rect.left() + nx * rect.width()
            py = rect.top() + ny * rect.height()
            painter.drawEllipse(int(px) - 3, int(py) - 3, 6, 6)

    def export_to_coco(self, image_id: int, ann_id: int, image_w: int,
                       image_h: int) -> dict:
        abs_points = []
        for x, y in self.points:
            abs_points.extend([x * image_w, y * image_h])
        return {
            "id": ann_id,
            "image_id": image_id,
            "category_id": 1,  # or map from self.id
            "segmentation": [abs_points],
            "area": 0,  # polygon area can be computed if needed
            "bbox": self._compute_bbox(image_w, image_h),
            "iscrowd": 0,
        }

    def _compute_bbox(self, image_w, image_h):
        xs = [x * image_w for x, _ in self.points]
        ys = [y * image_h for _, y in self.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return [min_x, min_y, max_x - min_x, max_y - min_y]
