# app/ui/overlay_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, List, Tuple
import uuid
from datetime import datetime
import logging

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QCursor, QKeySequence
from PySide6.QtWidgets import QWidget, QMessageBox, QApplication

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
MOVING_POINT_COLOR = QColor(255, 180, 0)  # highlight color for active vertex
ACTIVE_VERTEX_RADIUS_PX = 8  # pixel threshold to detect vertex hover


class OverlayWidget(QWidget):
    """Overlay for drawing boxes/polygons with full point editing support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        screen = QApplication.primaryScreen()
        dpi_x = screen.physicalDotsPerInchX()
        dpi_y = screen.physicalDotsPerInchY()
        self.screen_width_mm = screen.size().width() / dpi_x * 25.4
        self.screen_height_mm = screen.size().height() / dpi_y * 25.4

        self.main_window: MainWindow = None
        self.mode = "box"  # "box" or "poly"
        self.dragging = False
        self.last_mouse_pos: Optional[QPointF] = None
        self.highlighted_point_index: Optional[int] = None

        # Live drawing state
        self.current_mask: Optional[VectorMask] = None
        self.selected_mask: Optional[VectorMask] = None

        # vertex editing state
        self.active_vertex_index: Optional[int] = None
        self.dragging_vertex: bool = False

        # Animation
        self.dash_offset = DASH_OFFSET
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(ANIMATION_MSEC)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

        # Colors
        self.box_color = QColor(255, 250, 240)
        self.live_color = QColor(226, 61, 40)
        self.selected_color = QColor(160, 160, 160)

    def set_mode(self, mode: str):
        assert mode in ("box", "poly")
        self.mode = mode

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

    @staticmethod
    def find_nearest_vertex(mask: VectorMask, x_img_norm: float,
                            y_img_norm: float,
                            img_w: int, img_h: int, widget_w: int,
                            widget_h: int, rect) -> Tuple[Optional[int], float]:
        """Return (index, distance_in_pixels) of nearest vertex or (None, inf)."""
        best_idx = None
        best_dist = float("inf")

        norm_pts = mask.get_points()

        # Convert normalized points to widget coordinates
        cur_px = rect.left() + x_img_norm * rect.width()
        cur_py = rect.top() + y_img_norm * rect.height()

        for idx, (nx, ny) in enumerate(norm_pts):
            px = rect.left() + nx * rect.width()
            py = rect.top() + ny * rect.height()
            dist = ((px - cur_px) ** 2 + (py - cur_py) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        return best_idx, best_dist
    # -----------------------------
    # Mouse events (press/move/release)
    # -----------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() != Qt.MouseButton.LeftButton:
            return

        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)
        x_img, y_img = widget_to_image_coords(event.position(), img_w, img_h,
                                              widget_w, widget_h, rect)
        x_img_norm, y_img_norm = x_img / img_w, y_img / img_h

        # If we have a selected mask, check if we clicked near an active vertex
        if self.selected_mask:
            idx, dist = self.find_nearest_vertex(
                self.selected_mask,
                x_img_norm, y_img_norm,
                img_w, img_h, widget_w, widget_h,
                rect
            )

            if idx is not None and dist <= ACTIVE_VERTEX_RADIUS_PX:
                # Start dragging that vertex
                self.active_vertex_index = idx
                self.dragging_vertex = True
                self.last_mouse_pos = event.position()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return

            # If clicked inside the mask (but not on a vertex) -> start dragging whole mask
            if self.selected_mask.contains(x_img_norm, y_img_norm):
                self.dragging = True
                self.last_mouse_pos = event.position()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return

        # Otherwise: starting a new mask (deselect current)
        self.selected_mask = None
        self.active_vertex_index = None
        self.dragging = False
        self.dragging_vertex = False
        self.last_mouse_pos = None

        # Create a new current_mask using the VectorMask factory
        self.current_mask = VectorMask.create(self.mode, x_img_norm, y_img_norm)

        # Assign unique ID and timestamp
        try:
            self.current_mask.id = str(uuid.uuid4())
            self.current_mask.ts = int(datetime.now().timestamp())
        except Exception:
            pass

        # Sync toolbar mode with MainWindow
        try:
            self.main_window.set_draw_mode(self.mode)
        except Exception:
            pass

        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        img_w, img_h = self.main_window.image_width, self.main_window.image_height
        widget_w, widget_h = self.width(), self.height()
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)
        x_img, y_img = widget_to_image_coords(event.position(), img_w, img_h,
                                              widget_w, widget_h, rect)
        nx, ny = x_img / img_w, y_img / img_h

        # Hit test existing masks (from topmost)
        for mask in reversed(self.main_window.document.vector_masks):
            if mask.contains(nx, ny):
                self.selected_mask = mask
                self.current_mask = None  # stop drawing
                self.dragging = False
                self.active_vertex_index = None
                self.dragging_vertex = False
                self.update()
                return

        # Clicked empty space -> deselect mask and return to drawing mode
        self.selected_mask = None
        self.current_mask = None
        self.dragging = False
        self.active_vertex_index = None
        self.dragging_vertex = False
        self.set_mode("box")
        self.update()

    def keyPressEvent(self, event):
        # Delete selected point (if active) or delete mask
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_mask and self.active_vertex_index is not None:
                # delete vertex if supported
                deleted = self.selected_mask.delete_point(
                    self.active_vertex_index)
                if deleted:
                    # clamp selection state
                    self.active_vertex_index = None
                    # push onto document.action_stack for undo
                    self.main_window.document.action_stack.append(
                        self.selected_mask)
                self.update()
                return
            elif self.selected_mask:
                # delete whole mask
                self.main_window.document.delete_vector_mask(self.selected_mask)
                self.selected_mask = None
                self.active_vertex_index = None
                self.update()
                return

        # Undo/Redo shortcuts
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
        x_img, y_img = widget_to_image_coords(event.position(), img_w, img_h,
                                              widget_w, widget_h, rect)
        x_img_norm, y_img_norm = x_img / img_w, y_img / img_h

        # Dragging a vertex: move that point only
        if self.dragging_vertex and self.selected_mask and self.active_vertex_index is not None:
            self.selected_mask.move_point(
                self.active_vertex_index, x_img_norm, y_img_norm)
            self.last_mouse_pos = event.position()
            self.update()
            return

        # Dragging whole mask
        if self.dragging and self.selected_mask:
            dx = (
                     event.position().x() - self.last_mouse_pos.x()
                 ) / self.width()
            dy = (
                     event.position().y() - self.last_mouse_pos.y()
                 ) / self.height()
            self.selected_mask.move(dx, dy)
            self.last_mouse_pos = event.position()
            self.update()
            return

        # Live drawing (new mask)
        if self.current_mask:
            self.current_mask.update(x_img_norm, y_img_norm)
            self.update()
            return

        # Hover: highlight nearest vertex if any
        if self.selected_mask:
            idx, dist = self.find_nearest_vertex(
                self.selected_mask, x_img_norm, y_img_norm,
                img_w, img_h, widget_w, widget_h, rect
            )
            if idx is not None and dist <= ACTIVE_VERTEX_RADIUS_PX:
                if self.active_vertex_index != idx:
                    self.active_vertex_index = idx
                    self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
                    self.update()
            else:
                if self.active_vertex_index is not None:
                    self.active_vertex_index = None
                    self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                    self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Finish vertex dragging
        if self.dragging_vertex:
            self.dragging_vertex = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.last_mouse_pos = None
            if self.selected_mask:
                self.main_window.document.action_stack.append(
                    self.selected_mask)

        # Finish mask dragging
        elif self.dragging:
            self.dragging = False
            self.last_mouse_pos = None
            if self.selected_mask:
                self.main_window.document.action_stack.append(
                    self.selected_mask)

        # Finish live mask drawing
        elif self.current_mask:
            img_w, img_h = self.main_window.image_width, self.main_window.image_height
            appended = self.main_window.document.append_vector_mask(
                self.current_mask,
                image_width=img_w, image_height=img_h,
                screen_width_mm=self.screen_width_mm,
                screen_height_mm=self.screen_height_mm
            )
            if appended:
                self.selected_mask = self.main_window.document.vector_masks[-1]
            self.current_mask = None

        self.update()

    # -----------------------------
    # Painting
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

        # Draw selection feedback points (highlight active vertex if any)
        if self.selected_mask:
            # default color for points
            self.selected_mask.draw_points(painter, img_w, img_h, widget_w,
                                           widget_h, rect,
                                           active_index=self.active_vertex_index,
                                           color=self.selected_color)

            # if active vertex exists draw additional highlight circle
            if self.active_vertex_index is not None:
                # draw a stronger highlight circle using MOVING_POINT_COLOR
                self.selected_mask.draw_points(painter, img_w, img_h, widget_w,
                                               widget_h, rect,
                                               active_index=self.active_vertex_index,
                                               color=MOVING_POINT_COLOR)

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
            QMessageBox.StandardButton.Cancel,  # default button,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self.main_window.document.clear()
        self.update()
