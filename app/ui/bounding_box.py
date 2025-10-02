from dataclasses import dataclass
from dataclasses_json import dataclass_json

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor

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

    def __post_init__(self):
        self.selected = False

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

    def update(self, x_img_norm: float, y_img_norm: float):
        """Update width/height of bounding box based on mouse movement (normalized coords)."""
        self.w = abs(x_img_norm - self.x)
        self.h = abs(y_img_norm - self.y)
        self.x = min(self.x, x_img_norm)
        self.y = min(self.y, y_img_norm)
    def move(self, dx: float, dy: float):
        """Move box in normalized coordinates, clamped inside [0,1]."""
        self.x = min(max(self.x + dx, 0.0), 1.0 - self.w)
        self.y = min(max(self.y + dy, 0.0), 1.0 - self.h)

    def contains(self, nx: float, ny: float) -> bool:
        """Check if normalized point (nx,ny) is inside the box."""
        return (self.x <= nx <= self.x + self.w) and (
            self.y <= ny <= self.y + self.h)

    def draw_points(self, painter, img_w, img_h, widget_w, widget_h, rect,
                    color=QColor(180, 180, 180)):
        """Draw small grey squares at corners."""
        from PySide6.QtGui import QPen
        pen = QPen(color, 2)
        painter.setPen(pen)
        corners = [
            (self.x, self.y),
            (self.x + self.w, self.y),
            (self.x, self.y + self.h),
            (self.x + self.w, self.y + self.h),
        ]
        for nx, ny in corners:
            px = rect.left() + nx * rect.width()
            py = rect.top() + ny * rect.height()
            painter.drawEllipse(int(px) - 3, int(py) - 3, 6, 6)

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
