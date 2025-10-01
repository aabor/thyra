from dataclasses import dataclass
from dataclasses_json import dataclass_json

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen

from app.computational_geometry.coordinates_convertion import \
    image_to_widget_coords
from app.ui.vector_masks import VectorMask, register_vector_mask_object


@register_vector_mask_object
@dataclass_json
@dataclass
class BoundingBox(VectorMask):
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

    def export_to_coco(self, image_id: int, ann_id: int, image_w: int,
                       image_h: int) -> dict:
        return {
            "id": ann_id,
            "image_id": image_id,
            "category_id": 1,  # you may want to map from self.id
            "bbox": [
                self.x * image_w,
                self.y * image_h,
                self.w * image_w,
                self.h * image_h
            ],
            "area": (self.w * image_w) * (self.h * image_h),
            "iscrowd": 0,
            "segmentation": [self.to_polygon()],  # polygon in absolute coords
        }

    def to_polygon(self):
        # COCO segmentation expects absolute coords
        return [
            self.x, self.y,
            self.x + self.w, self.y,
            self.x + self.w, self.y + self.h,
            self.x, self.y + self.h,
        ]
