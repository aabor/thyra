import uuid
from typing import List, Tuple

from PySide6.QtCore import Qt, QPointF, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
from PySide6.QtWidgets import QWidget

from app.ui.vector_masks import BoundingBox, PolygonShape

PEN_WIDTH = 2

DASH_OFFSET = 0.0

ANIMATION_MSEC = 30


class OverlayWidget(QWidget):
    """Transparent overlay for drawing boxes and polygons with improved polygon UX."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self.boxes: List[BoundingBox] = []
        self.polygons: List[PolygonShape] = []

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
            # append new points as user drags
            self.current_poly.append((event.position().x(), event.position().y()))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drawing_box and self.mode == "box":
                self.drawing_box = False
                p1, p2 = self.box_start, self.box_current
                x, y = min(p1.x(), p2.x()), min(p1.y(), p2.y())
                w, h = abs(p2.x() - p1.x()), abs(p2.y() - p1.y())
                if w > 5 and h > 5:
                    self.boxes.append(BoundingBox(x, y, w, h, str(uuid.uuid4())))
            elif self.drawing_poly and self.mode == "poly":
                # finish polygon on mouse release
                if len(self.current_poly) >= 3:
                    self.polygons.append(
                        PolygonShape(list(self.current_poly), str(uuid.uuid4()))
                    )
                self.drawing_poly = False
                self.current_poly = []
        self.update()

    # -----------------------------
    # Animation timer
    # -----------------------------
    def _on_anim_tick(self):
        self.dash_offset -= 1.5
        if self.dash_offset < -1000:
            self.dash_offset = 0
        self.update()

    # -----------------------------
    # Clear shapes
    # -----------------------------
    def clear_shapes(self):
        self.boxes = []
        self.polygons = []
        self.update()

    # -----------------------------
    # Paint
    # -----------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw existing polygons
        for poly in self.polygons:
            if len(poly.points) < 3:
                continue
            qpoints = [QPointF(x, y) for x, y in poly.points]
            pen = QPen(self.box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([6.0, 6.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF(qpoints))

        # Draw existing bounding boxes
        for box in self.boxes:
            rect = QRectF(box.x, box.y, box.w, box.h)
            pen = QPen(self.box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # Live box preview
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

        # Live polygon preview
        if self.drawing_poly and self.current_poly:
            pts = [QPointF(x, y) for x, y in self.current_poly]
            if len(pts) >= PEN_WIDTH:
                pen = QPen(self.live_box_color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6.0, 6.0])
                pen.setDashOffset(self.dash_offset)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF(pts))
            # draw small feedback points
            for p in pts:
                painter.setBrush(QBrush(self.feedback_point_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(p, 3, 3)