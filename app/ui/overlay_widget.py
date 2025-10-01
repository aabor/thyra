from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import uuid
from typing import List
from datetime import datetime
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget, QMessageBox

from app.computational_geometry.coordinates_convertion import \
    widget_to_image_coords, compute_video_rect
from app.ui.polygone_shape import PolygonShape
from app.ui.bounding_box import BoundingBox
from app.ui.vector_masks import VectorMask

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
        self.mode = "box"  # "box" or "poly"

        # Live drawing state
        self.current_mask: Optional[VectorMask] = None

        # Animation
        self.dash_offset = DASH_OFFSET
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(ANIMATION_MSEC)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

        # Colors
        self.box_color = QColor(255, 250, 240)
        self.live_color = QColor(226, 61, 40)

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

    def _on_anim_tick(self):
        self.dash_offset += 1.0
        if self.dash_offset > 12.0:
            self.dash_offset = 0.0
        self.update()


    # -----------------------------
    # Mouse events
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h, rect
        )

        ts = int(datetime.now().timestamp())
        if self.mode == "box":
            # Start a new bounding box
            self.current_mask = BoundingBox(
                x=x_img / img_w, y=y_img / img_h, w=0.0, h=0.0,
                id=str(uuid.uuid4()), ts=ts
            )
        else:
            # Start a new polygon
            self.current_mask = PolygonShape(
                points=[(x_img / img_w, y_img / img_h)],
                id=str(uuid.uuid4()), ts=ts
            )
        self.update()

    def mouseMoveEvent(self, event):
        if not self.current_mask:
            return
        img_w = self.main_window.image_width
        img_h = self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h, rect
        )

        if isinstance(self.current_mask, BoundingBox):
            # Update w/h relative to start point
            self.current_mask.w = abs(x_img / img_w - self.current_mask.x)
            self.current_mask.h = abs(y_img / img_h - self.current_mask.y)
            self.current_mask.x = min(self.current_mask.x, x_img / img_w)
            self.current_mask.y = min(self.current_mask.y, y_img / img_h)
        elif isinstance(self.current_mask, PolygonShape):
            last_x, last_y = self.current_mask.points[-1]
            if abs(last_x - x_img / img_w) > 0.002 or abs(last_y - y_img / img_h) > 0.002:
                self.current_mask.points.append((x_img / img_w, y_img / img_h))

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self.current_mask:
            return

        # Only keep if valid
        if isinstance(self.current_mask, BoundingBox):
            if self.current_mask.w > 0.01 and self.current_mask.h > 0.01:
                self.main_window.document.vector_masks.append(self.current_mask)
        elif isinstance(self.current_mask, PolygonShape):
            if len(self.current_mask.points) >= 3:
                self.main_window.document.vector_masks.append(self.current_mask)

        self.current_mask = None
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
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

        # Draw finished masks
        pen = self._make_dash_pen(self.box_color, [8.0, 4.0])
        for mask in self.main_window.document.vector_masks:
            mask.draw(painter, img_w, img_h, widget_w, widget_h, rect, pen)

        # Draw live mask
        if self.current_mask:
            pen_live = self._make_dash_pen(self.live_color, [6.0, 6.0])
            self.current_mask.draw(painter, img_w, img_h, widget_w, widget_h, rect, pen_live)
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
    # def _on_anim_tick(self):
    #     self.dash_offset -= 1.5
    #     if self.dash_offset < -1000:
    #         self.dash_offset = 0
    #     # only trigger a repaint if visible
    #     if self.isVisible():
    #         self.update()
