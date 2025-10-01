from __future__ import annotations

from typing import TYPE_CHECKING, Any
import uuid
from typing import List, Tuple
from datetime import datetime
import logging

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
from PySide6.QtWidgets import QWidget, QMessageBox

from app.computational_geometry.coordinates_convertion import \
    widget_to_image_coords, compute_video_rect, image_to_widget_coords
from app.ui.polygone_shape import PolygonShape
from app.ui.bounding_box import BoundingBox

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow
else:
    MainWindow = Any

logger = logging.getLogger(__name__)

PEN_WIDTH = 2
DASH_OFFSET = 0.0
ANIMATION_MSEC = 30


class OverlayWidget(QWidget):
    """Overlay for drawing boxes/polygons with proper scaling for images and videos.

    Notes:
    - Documents store shapes in normalized *image* coordinates: x,y,w,h in [0..1]
      and polygon points as [(x,y), ...] with x,y normalized.
    - This overlay converts between widget coordinates and image coords using
      the actual image rectangle inside the widget (letterbox/padding).
    - Live drawing uses absolute image coordinates internally (not normalized)
      and final shapes are saved normalized.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          False)
        self.setMouseTracking(True)

        self.main_window: MainWindow = None

        # Live drawing state (use *image* coordinates for live storage)
        self.drawing_box = False
        self.box_start_img: Tuple[float, float] = (
            0.0, 0.0)  # absolute image coords
        self.box_current_img: Tuple[float, float] = (
            0.0, 0.0)  # absolute image coords

        self.drawing_poly = False
        self.current_poly_img: List[
            Tuple[float, float]] = []  # absolute image coords

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
    # Helpers: pens / pens factory
    # -----------------------------
    def _make_dash_pen(self, color: QColor, dash_pattern: List[float]) -> QPen:
        pen = QPen(color, PEN_WIDTH, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern(dash_pattern)
        pen.setDashOffset(self.dash_offset)
        return pen

    def sizeHint(self):
        return self.parent().size()

    # -----------------------------
    # Mouse events (use image coords for live state)
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()

        # get absolute image coords for the press position
        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h)

        if self.mode == "box":
            self.drawing_box = True
            self.box_start_img = (x_img, y_img)
            self.box_current_img = (x_img, y_img)
        else:
            self.drawing_poly = True
            self.current_poly_img = [(x_img, y_img)]
        self.update()

    def mouseMoveEvent(self, event):
        # update live coordinates in image space (if drawing)
        if not (self.drawing_box or self.drawing_poly):
            return
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()

        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h, rect)

        if self.drawing_box:
            self.box_current_img = (x_img, y_img)
        elif self.drawing_poly:
            # append successive points (image coords)
            # avoid extremely dense appends — only append if moved at least 1 px in image coords
            last = self.current_poly_img[-1] if self.current_poly_img else (
                None, None)
            if last[0] is None or abs(last[0] - x_img) >= 1.0 or abs(
                last[1] - y_img) >= 1.0:
                self.current_poly_img.append((x_img, y_img))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        ts = int(datetime.now().timestamp())
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height

        if img_w <= 0 or img_h <= 0:
            # nothing to save
            self.drawing_box = False
            self.drawing_poly = False
            self.current_poly_img = []
            return

        if self.drawing_box and self.mode == "box":
            self.drawing_box = False
            p1 = self.box_start_img
            p2 = self.box_current_img
            x_abs, y_abs = min(p1[0], p2[0]), min(p1[1], p2[1])
            w_abs, h_abs = abs(p2[0] - p1[0]), abs(p2[1] - p1[1])
            if w_abs > 5 and h_abs > 5:
                # convert to normalized image coords and append to document
                norm_box = BoundingBox(
                    x=x_abs / img_w,
                    y=y_abs / img_h,
                    w=w_abs / img_w,
                    h=h_abs / img_h,
                    id=str(uuid.uuid4()),
                    ts=ts
                )
                self.main_window.document.vector_masks.append(norm_box)

        elif self.drawing_poly and self.mode == "poly":
            self.drawing_poly = False
            if len(self.current_poly_img) >= 3:
                norm_points = [(x / img_w, y / img_h) for (x, y) in
                               self.current_poly_img]
                norm_poly = PolygonShape(points=norm_points,
                                         id=str(uuid.uuid4()),
                                         ts=ts)
                self.main_window.document.vector_masks.append(norm_poly)
            self.current_poly_img = []

        self.update()

    # -----------------------------
    # Paint
    # -----------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()

        # compute rect ONCE per paint
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

        # -----------------------------
        # Draw vector masks (document stores normalized coords)
        # -----------------------------
        pen = self._make_dash_pen(self.box_color, [8.0, 4.0])
        for vector_mask in self.main_window.document.vector_masks:
            vector_mask.draw(painter, img_w, img_h,
                             widget_w, widget_h, rect, pen)

        # -----------------------------
        # Live box preview (use image coords stored during drawing)
        # -----------------------------
        if self.drawing_box and self.mode == "box":
            try:
                p1_widget = image_to_widget_coords(
                    self.box_start_img[0], self.box_start_img[1],
                    img_w, img_h, widget_w, widget_h, rect)
                p2_widget = image_to_widget_coords(
                    self.box_current_img[0], self.box_current_img[1],
                    img_w, img_h, widget_w, widget_h, rect)
                live_rect = QRectF(p1_widget, p2_widget)
                pen_live = self._make_dash_pen(self.live_box_color, [8.0, 4.0])
                painter.setPen(pen_live)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(live_rect)
            except Exception:
                pass

        # -----------------------------
        # Live polygon preview (use image coords stored during drawing)
        # -----------------------------
        if self.drawing_poly and self.current_poly_img:
            try:
                pts_widget = [image_to_widget_coords(
                    x, y, img_w, img_h, widget_w, widget_h, rect) for x, y
                    in self.current_poly_img]
                if len(pts_widget) >= 2:
                    pen_live_poly = self._make_dash_pen(self.live_box_color,
                                                        [6.0, 6.0])
                    painter.setPen(pen_live_poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPolyline(QPolygonF(pts_widget))
                for p in pts_widget:
                    painter.setBrush(QBrush(self.feedback_point_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(p, 3, 3)
            except Exception:
                pass

    # -----------------------------
    # Undo / Redo / Clear
    # -----------------------------
    def undo(self):
        self.main_window.document.undo()
        self.update()

    def redo(self):
        if self.main_window.document.redo():
            self.update()

    def clear_shapes(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "This action can't be undone!",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,  # default button
        )
        if reply == QMessageBox.StandardButton.Ok:
            self.main_window.document.clear()
        self.update()

    # -----------------------------
    # Animation
    # -----------------------------
    def _on_anim_tick(self):
        self.dash_offset -= 1.5
        if self.dash_offset < -1000:
            self.dash_offset = 0
        # only trigger a repaint if visible
        if self.isVisible():
            self.update()
