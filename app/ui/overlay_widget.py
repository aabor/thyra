from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union
import uuid
from typing import List, Tuple
from datetime import datetime
import logging

from PySide6.QtCore import Qt, QPointF, QTimer, QRectF, QRect
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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self.main_window: MainWindow = None
        self.action_stack: List[Union[BoundingBox, PolygonShape]] = []

        # Live drawing state (use *image* coordinates for live storage)
        self.drawing_box = False
        self.box_start_img: Tuple[float, float] = (0.0, 0.0)   # absolute image coords
        self.box_current_img: Tuple[float, float] = (0.0, 0.0)  # absolute image coords

        self.drawing_poly = False
        self.current_poly_img: List[Tuple[float, float]] = []  # absolute image coords

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

    # -----------------------------
    # Video/Image rectangle mapping
    # -----------------------------
    def _compute_video_rect(self) -> QRectF:
        """Compute rectangle (in widget coordinates) where the image/video is drawn.

        Centers and scales the image to fit while preserving aspect ratio (letterbox).
        """
        widget_w, widget_h = self.width(), self.height()

        img_w = getattr(self.main_window, "image_width", 0) or 0
        img_h = getattr(self.main_window, "image_height", 0) or 0

        if img_w <= 0 or img_h <= 0:
            return QRectF(0, 0, widget_w, widget_h)

        widget_ratio = widget_w / widget_h
        img_ratio = img_w / img_h

        if widget_ratio > img_ratio:
            # Widget is wider -> fit height, center horizontally
            height = widget_h
            width = img_ratio * height
            x_offset = (widget_w - width) / 2.0
            y_offset = 0.0
        else:
            # Widget is taller -> fit width, center vertically
            width = widget_w
            height = width / img_ratio
            x_offset = 0.0
            y_offset = (widget_h - height) / 2.0

        return QRectF(x_offset, y_offset, width, height)

    def widget_to_image_coords(self, pos: QPointF, rect: QRectF | None = None) -> Tuple[float, float]:
        """Map widget coordinates -> absolute image coordinates (pixels).

        Accepts optional precomputed rect to avoid recomputing inside paint loops.
        """
        if rect is None:
            rect = self._compute_video_rect()

        img_w = getattr(self.main_window, "image_width", 0) or 0
        img_h = getattr(self.main_window, "image_height", 0) or 0
        if img_w <= 0 or img_h <= 0:
            return 0.0, 0.0

        # relative coords inside image rect
        x_rel = (pos.x() - rect.x()) / rect.width()
        y_rel = (pos.y() - rect.y()) / rect.height()

        # clamp to [0,1]
        x_rel = min(max(0.0, x_rel), 1.0)
        y_rel = min(max(0.0, y_rel), 1.0)

        # convert to absolute image pixels
        x_img = x_rel * img_w
        y_img = y_rel * img_h
        return x_img, y_img

    def image_to_widget_coords(self, x_img: float, y_img: float, rect: QRectF | None = None) -> QPointF:
        """Map absolute image coordinates (pixels) -> widget coordinates (QPointF)."""
        if rect is None:
            rect = self._compute_video_rect()

        img_w = getattr(self.main_window, "image_width", 0) or 0
        img_h = getattr(self.main_window, "image_height", 0) or 0
        if img_w <= 0 or img_h <= 0:
            return QPointF(0.0, 0.0)

        x_rel = x_img / img_w
        y_rel = y_img / img_h

        x_widget = rect.x() + x_rel * rect.width()
        y_widget = rect.y() + y_rel * rect.height()
        return QPointF(x_widget, y_widget)

    def sizeHint(self):
        return self.parent().size()

    # -----------------------------
    # Mouse events (use image coords for live state)
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        rect = self._compute_video_rect()
        # get absolute image coords for the press position
        x_img, y_img = self.widget_to_image_coords(event.position(), rect)

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

        rect = self._compute_video_rect()
        x_img, y_img = self.widget_to_image_coords(event.position(), rect)

        if self.drawing_box:
            self.box_current_img = (x_img, y_img)
        elif self.drawing_poly:
            # append successive points (image coords)
            # avoid extremely dense appends — only append if moved at least 1 px in image coords
            last = self.current_poly_img[-1] if self.current_poly_img else (None, None)
            if last[0] is None or abs(last[0] - x_img) >= 1.0 or abs(last[1] - y_img) >= 1.0:
                self.current_poly_img.append((x_img, y_img))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        ts = int(datetime.now().timestamp())
        img_w = getattr(self.main_window, "image_width", 0) or 0
        img_h = getattr(self.main_window, "image_height", 0) or 0
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
                    id=str(uuid.uuid4())
                )
                self.main_window.document.boxes.append((ts, norm_box))

        elif self.drawing_poly and self.mode == "poly":
            self.drawing_poly = False
            if len(self.current_poly_img) >= 3:
                norm_points = [(x / img_w, y / img_h) for (x, y) in self.current_poly_img]
                norm_poly = PolygonShape(points=norm_points, id=str(uuid.uuid4()))
                self.main_window.document.polygons.append((ts, norm_poly))
            self.current_poly_img = []

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

    # -----------------------------
    # Undo / Redo / Clear
    # -----------------------------
    def undo(self):
        latest_ts = -1
        latest_kind = None
        latest_index = None

        for idx, entry in enumerate(self.main_window.document.boxes):
            try:
                ts = int(entry[0])
            except Exception:
                continue
            if ts > latest_ts:
                latest_ts = ts
                latest_kind = "box"
                latest_index = idx

        for idx, entry in enumerate(self.main_window.document.polygons):
            try:
                ts = int(entry[0])
            except Exception:
                continue
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

        # compute rect ONCE per paint
        rect = self._compute_video_rect()

        # convenience values
        img_w = getattr(self.main_window, "image_width", 0) or 0
        img_h = getattr(self.main_window, "image_height", 0) or 0

        # -----------------------------
        # Draw stored boxes (document stores normalized coords)
        # -----------------------------
        pen_box = self._make_dash_pen(self.box_color, [8.0, 4.0])
        for _, box in self.main_window.document.boxes:
            try:
                # box.x etc are normalized in [0..1]
                x_abs = box.x * img_w
                y_abs = box.y * img_h
                w_abs = box.w * img_w
                h_abs = box.h * img_h
                p1 = self.image_to_widget_coords(x_abs, y_abs, rect)
                p2 = self.image_to_widget_coords(x_abs + w_abs, y_abs + h_abs, rect)
                draw_rect = QRectF(p1, p2)
                painter.setPen(pen_box)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(draw_rect)
            except Exception:
                continue

        # -----------------------------
        # Draw stored polygons (normalized points)
        # -----------------------------
        pen_poly = self._make_dash_pen(self.box_color, [6.0, 6.0])
        for _, poly in self.main_window.document.polygons:
            try:
                pts = [self.image_to_widget_coords(x * img_w, y * img_h, rect) for x, y in poly.points]
                if len(pts) >= 3:
                    painter.setPen(pen_poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPolygon(QPolygonF(pts))
                # feedback small points
                for p in pts:
                    painter.setBrush(QBrush(self.feedback_point_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(p, 3, 3)
            except Exception:
                continue

        # -----------------------------
        # Live box preview (use image coords stored during drawing)
        # -----------------------------
        if self.drawing_box and self.mode == "box":
            try:
                p1_widget = self.image_to_widget_coords(self.box_start_img[0], self.box_start_img[1], rect)
                p2_widget = self.image_to_widget_coords(self.box_current_img[0], self.box_current_img[1], rect)
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
                pts_widget = [self.image_to_widget_coords(x, y, rect) for x, y in self.current_poly_img]
                if len(pts_widget) >= 2:
                    pen_live_poly = self._make_dash_pen(self.live_box_color, [6.0, 6.0])
                    painter.setPen(pen_live_poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPolyline(QPolygonF(pts_widget))
                for p in pts_widget:
                    painter.setBrush(QBrush(self.feedback_point_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(p, 3, 3)
            except Exception:
                pass