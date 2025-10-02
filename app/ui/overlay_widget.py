from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from typing import List
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QKeySequence
from PySide6.QtWidgets import QWidget, QMessageBox

from app.computational_geometry.coordinates_convertion import \
    widget_to_image_coords, compute_video_rect
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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.main_window: MainWindow = None
        self.mode = "box"  # "box" or "poly"
        self.dragging = False
        self.last_mouse_pos = None

        # Live drawing state
        self.current_mask: Optional[VectorMask] = None
        self.selected_mask: Optional[VectorMask] = None

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
        self.setFocus()
        if event.button() != Qt.MouseButton.LeftButton:
            return

        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)
        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h, rect
        )
        x_img_norm, y_img_norm = x_img / img_w, y_img / img_h

        # Start dragging existing mask if selected
        if self.selected_mask and self.selected_mask.contains(x_img_norm,
                                                              y_img_norm):
            self.dragging = True
            self.last_mouse_pos = event.position()
            return

        # Otherwise, start drawing a new mask
        self.dragging = False
        self.last_mouse_pos = None
        self.current_mask = VectorMask.create(self.mode, x_img_norm, y_img_norm)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)
        nx, ny = widget_to_image_coords(event.position(), img_w, img_h,
                                        widget_w, widget_h, rect)
        nx, ny = nx / img_w, ny / img_h

        # Hit test existing masks (from topmost)
        for mask in reversed(self.main_window.document.vector_masks):
            if mask.contains(nx, ny):
                self.selected_mask = mask
                self.current_mask = None  # stop drawing
                self.dragging = False
                self.update()
                return

        # Clicked empty space -> deselect mask and return to drawing mode
        self.selected_mask = None
        self.current_mask = None
        self.dragging = False
        self.set_mode("box")  # reset to drawing boxes
        self.update()

    def keyPressEvent(self, event):
        if self.selected_mask and event.key() in (
            Qt.Key.Key_Delete, Qt.Key.Key_Backspace
        ):
            self.main_window.document.delete_vector_mask(self.selected_mask)
            self.selected_mask = None
            self.update()
            return

        # Undo/Redo
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo()
            return

        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)
        x_img, y_img = widget_to_image_coords(
            event.position(), img_w, img_h, widget_w, widget_h, rect
        )
        x_img_norm, y_img_norm = x_img / img_w, y_img / img_h

        # Move selected mask
        if self.dragging and self.selected_mask:
            dx = (event.position().x() - self.last_mouse_pos.x()) / self.width()
            dy = (
                     event.position().y() - self.last_mouse_pos.y()) / self.height()
            self.selected_mask.move(dx, dy)
            self.last_mouse_pos = event.position()
            self.update()
            return

        # Update live drawing
        if self.current_mask:
            self.current_mask.update(x_img_norm, y_img_norm)
            self.update()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.dragging:
            self.dragging = False
            self.last_mouse_pos = None
        elif self.current_mask:
            self.main_window.document.append_vector_mask(self.current_mask)
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
            self.current_mask.draw(painter, img_w, img_h, widget_w, widget_h,
                                   rect, pen_live)

        # Draw selection feedback points
        if self.selected_mask:
            self.selected_mask.draw_points(
                painter, img_w, img_h, widget_w, widget_h, rect)

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
