from dataclasses_json import dataclass_json
from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF

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

    def export_to_coco(self, image_id: int, ann_id: int, image_w: int, image_h: int) -> dict:
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
