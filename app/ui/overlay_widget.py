from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union
import uuid
from typing import List, Tuple
from datetime import datetime
import logging

from PySide6.QtCore import Qt, QPointF, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
from PySide6.QtWidgets import QWidget

from app.ui.vector_masks import BoundingBox, PolygonShape

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow
else:
    MainWindow = Any

logger = logging.getLogger(__name__)

PEN_WIDTH = 2
DASH_OFFSET = 0.0
ANIMATION_MSEC = 30


class OverlayWidget(QWidget):
    """Overlay for drawing boxes/polygons using normalized image coordinates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self.main_window: MainWindow = None
        self.action_stack: List[Union[BoundingBox, PolygonShape]] = []

        self.drawing_box = False
        self.box_start = QPointF()
        self.box_current = QPointF()

        self.drawing_poly = False
        self.current_poly: List[Tuple[float, float]] = []

        self.dash_offset = DASH_OFFSET
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(ANIMATION_MSEC)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

        self.mode = "box"
        self.box_color = QColor(255, 250, 240)
        self.live_box_color = QColor(226, 61, 40)
        self.feedback_point_color = QColor(240, 128, 128)

    def set_mode(self, mode: str):
        assert mode in ("box", "poly")
        self.mode = mode

    # -----------------------------
    # Coordinate mapping
    # -----------------------------
    def widget_to_image_coords(self, pos: QPointF) -> Tuple[float, float]:
        """Map widget coordinates to image coordinates (taking scaling into account)."""
        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        canvas_w, canvas_h = self.width(), self.height()
        scale_x = img_w / canvas_w
        scale_y = img_h / canvas_h
        x_img = pos.x() * scale_x
        y_img = pos.y() * scale_y
        return x_img, y_img

    # -----------------------------
    # Mouse events
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "box":
                self.drawing_box = True
                self.box_start = event.position()
                self.box_current = event.position()
            else:  # polygon
                self.drawing_poly = True
                self.current_poly = [(event.position().x(), event.position().y())]
        self.update()

    def mouseMoveEvent(self, event):
        if self.drawing_box:
            self.box_current = event.position()
        elif self.drawing_poly:
            self.current_poly.append((event.position().x(), event.position().y()))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ts = int(datetime.now().timestamp())
            image_w, image_h = self.main_window.image_width, self.main_window.image_height

            if self.drawing_box and self.mode == "box":
                self.drawing_box = False
                p1_img = self.widget_to_image_coords(self.box_start)
                p2_img = self.widget_to_image_coords(self.box_current)
                x, y = min(p1_img[0], p2_img[0]), min(p1_img[1], p2_img[1])
                w, h = abs(p2_img[0] - p1_img[0]), abs(p2_img[1] - p1_img[1])
                if w > 5 and h > 5:
                    # convert to normalized image coordinates
                    norm_box = BoundingBox(
                        x=x / image_w,
                        y=y / image_h,
                        w=w / image_w,
                        h=h / image_h,
                        id=str(uuid.uuid4())
                    )
                    self.main_window.document.boxes.append((ts, norm_box))

            elif self.drawing_poly and self.mode == "poly":
                if len(self.current_poly) >= 3:
                    norm_points = []
                    for pt in self.current_poly:
                        x_img, y_img = self.widget_to_image_coords(QPointF(pt[0], pt[1]))
                        norm_points.append((x_img / image_w, y_img / image_h))
                    norm_poly = PolygonShape(points=norm_points, id=str(uuid.uuid4()))
                    self.main_window.document.polygons.append((ts, norm_poly))
                self.drawing_poly = False
                self.current_poly = []

        self.update()

    # -----------------------------
    # Animation
    # -----------------------------
    def _on_anim_tick(self):
        self.dash_offset -= 1.5
        if self.dash_offset < -1000:
            self.dash_offset = 0
        self.update()

    # -----------------------------
    # Undo / Redo / Clear
    # -----------------------------
    def undo(self):
        latest_ts = -1
        latest_kind = None
        latest_index = None

        for idx, entry in enumerate(self.main_window.document.boxes):
            ts = entry[0]
            if ts > latest_ts:
                latest_ts = ts
                latest_kind = "box"
                latest_index = idx
        for idx, entry in enumerate(self.main_window.document.polygons):
            ts = entry[0]
            if ts > latest_ts:
                latest_ts = ts
                latest_kind = "poly"
                latest_index = idx

        if latest_kind is None:
            return

        if latest_kind == "box":
            item = self.main_window.document.boxes.pop(latest_index)
        else:
            item = self.main_window.document.polygons.pop(latest_index)
        self.action_stack.append(item)
        self.update()

    def redo(self):
        if not self.action_stack:
            return
        item = self.action_stack.pop()
        ts, shape = item
        if isinstance(shape, BoundingBox):
            self.main_window.document.boxes.append((ts, shape))
        elif isinstance(shape, PolygonShape):
            self.main_window.document.polygons.append((ts, shape))
        self.update()

    def clear_shapes(self):
        self.main_window.document.boxes = []
        self.main_window.document.polygons = []
        self.update()

    # -----------------------------
    # Paint
    # -----------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas_w = self.width()
        canvas_h = self.height()
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        scale_x = canvas_w / img_w
        scale_y = canvas_h / img_h

        # draw boxes
        for _, box in self.main_window.document.boxes:
            rect = QRectF(box.x * img_w * scale_x, box.y * img_h * scale_y,
                          box.w * img_w * scale_x, box.h * img_h * scale_y)
            pen = QPen(self.box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # draw polygons
        for _, poly in self.main_window.document.polygons:
            pts = [QPointF(x * img_w * scale_x, y * img_h * scale_y) for x, y in poly.points]
            if len(pts) >= 3:
                pen = QPen(self.box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6.0, 6.0])
                pen.setDashOffset(self.dash_offset)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(QPolygonF(pts))
            # feedback points
            for p in pts:
                painter.setBrush(QBrush(self.feedback_point_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(p, 3, 3)

        # live box preview
        if self.drawing_box and self.mode == "box":
            p1, p2 = self.box_start, self.box_current
            rect = QRectF(min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                          abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))
            pen = QPen(self.live_box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # live polygon preview
        if self.drawing_poly and self.current_poly:
            pts = [QPointF(x, y) for x, y in self.current_poly]
            if len(pts) >= PEN_WIDTH:
                pen = QPen(self.live_box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6.0, 6.0])
                pen.setDashOffset(self.dash_offset)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF(pts))
            for p in pts:
                painter.setBrush(QBrush(self.feedback_point_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(p, 3, 3)