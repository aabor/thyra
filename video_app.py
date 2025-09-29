#!/usr/bin/env python3
"""
Toy PySide6 app embedding libVLC with interactive overlays and COCO export.

Features:
- Start maximized (not fullscreen)
- Load video files from ~/Thyra/video
- Play/pause/stop via QAction toolbar
- Status bar shows opened file path
- Draw bounding boxes (click-drag)
- Draw freeform closed polygon (click to add points, double-click to close)
- Live preview during drawing
- Animated dashed grey outline (counterclockwise appearance via dash offset)
- Save shapes to COCO JSON in ~/Thyra/
- Cross-platform video output attach snippet included
"""

import sys
import os
import json
import math
import uuid
from dataclasses import dataclass, asdict
from typing import List, Tuple

# Ensure spawn regime if any multiprocessing is used later (cross-platform safety)
try:
    import multiprocessing

    multiprocessing.set_start_method('spawn', force=False)
except Exception:
    # harmless if already set or not applicable
    pass

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFileDialog,
    QToolBar, QLabel, QStatusBar
)
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QAction

import vlc  # python-vlc

HOME = os.path.expanduser("~")
THYRA_DIR = os.path.join(HOME, "Thyra")
THYRA_VIDEO_DIR = os.path.join(THYRA_DIR, "video")
os.makedirs(THYRA_VIDEO_DIR, exist_ok=True)
os.makedirs(THYRA_DIR, exist_ok=True)


@dataclass
class BoundingBox:
    x: float
    y: float
    w: float
    h: float
    id: str

    def to_coco_bbox(self):
        return [self.x, self.y, self.w, self.h]

    def to_polygon(self):
        x, y, w, h = self.x, self.y, self.w, self.h
        return [x, y, x + w, y, x + w, y + h, x, y + h]


@dataclass
class PolygonShape:
    points: List[Tuple[float, float]]
    id: str

    def to_coco_segmentation(self):
        # single segmentation list (flattened)
        flattened = []
        for (x, y) in self.points:
            flattened.extend([x, y])
        return [flattened]  # COCO expects list of lists


class VideoFrameWidget(QWidget):
    """Widget that will act as the container for VLC video output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Allow stacking overlay widgets on top
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMinimumSize(320, 240)


class OverlayWidget(QWidget):
    """Transparent widget on top of the video widget for drawing shapes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Accept mouse events so user can draw
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Shapes storage
        self.boxes: List[BoundingBox] = []
        self.polygons: List[PolygonShape] = []

        # Drawing state
        self.drawing_box = False
        self.box_start = QPointF()
        self.box_current = QPointF()

        self.drawing_poly = False
        self.current_poly: List[Tuple[float, float]] = []

        # Animation for dashed outline
        self.dash_offset = 0.0
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(30)  # ~33 fps for smooth dash movement
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

        # Mode: "box" or "poly"
        self.mode = "box"

    def set_mode(self, mode: str):
        assert mode in ("box", "poly")
        self.mode = mode

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "box":
                self.drawing_box = True
                self.box_start = event.position()
                self.box_current = event.position()
                self.update()
            else:  # poly
                if not self.drawing_poly:
                    self.drawing_poly = True
                    self.current_poly = []
                self.current_poly.append(
                    (event.position().x(), event.position().y()))
                self.update()

    def mouseMoveEvent(self, event):
        if self.drawing_box:
            self.box_current = event.position()
            self.update()
        else:
            # For poly, we still want live preview of segment to mouse pos
            if self.drawing_poly:
                # We store mouse pos in a temporary last point via attribute
                self._mouse_pos = (event.position().x(), event.position().y())
                self.update()

    def mouseDoubleClickEvent(self, event):
        if self.mode == "poly" and self.drawing_poly:
            # close polygon
            if len(self.current_poly) >= 3:
                poly = PolygonShape(points=list(self.current_poly),
                                    id=str(uuid.uuid4()))
                self.polygons.append(poly)
            self.drawing_poly = False
            self.current_poly = []
            self.update()

    def keyPressEvent(self, event):
        if self.mode == "poly" and self.drawing_poly:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if len(self.current_poly) >= 3:
                    poly = PolygonShape(points=list(self.current_poly),
                                        id=str(uuid.uuid4()))
                    self.polygons.append(poly)
                self.drawing_poly = False
                self.current_poly = []
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_box and \
            self.mode == "box":
            self.drawing_box = False
            p1 = self.box_start
            p2 = self.box_current
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())
            # ignore too small
            if w > 5 and h > 5:
                box = BoundingBox(x=x, y=y, w=w, h=h, id=str(uuid.uuid4()))
                self.boxes.append(box)
            self.update()

    def _on_anim_tick(self):
        # Move the dash offset to create counterclockwise moving dashes visual
        # subtracting offset -> dashes move CCW visually
        self.dash_offset -= 1.5
        if self.dash_offset < -1000:
            self.dash_offset = 0.0
        self.update()

    def clear_shapes(self):
        self.boxes = []
        self.polygons = []
        self.update()


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # -----------------------------
        # Draw existing polygons
        # -----------------------------
        for poly in self.polygons:
            qpoints = [QPointF(x, y) for (x, y) in poly.points]
            if len(qpoints) < 3:
                continue

            # Fill translucent (transparent)
            brush = QBrush(QColor(0, 0, 0, 30))  # alpha 30
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(*qpoints)

            # Animated dashed outline
            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([6.0, 6.0])
            pen.setDashOffset(self.dash_offset)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawPolygon(*qpoints)

        # -----------------------------
        # Draw existing bounding boxes
        # -----------------------------
        for box in self.boxes:
            rect = QRectF(box.x, box.y, box.w, box.h)

            # Fill transparent
            painter.setBrush(QBrush(QColor(0, 0, 0, 30)))  # alpha 30
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

            # Animated dashed outline
            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawRect(rect)

        # -----------------------------
        # Live-drawing preview for box
        # -----------------------------
        if self.drawing_box and self.mode == "box":
            p1, p2 = self.box_start, self.box_current
            rect = QRectF(min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                          abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))

            # Transparent fill
            painter.setBrush(QBrush(QColor(0, 0, 0, 20)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

            # Dashed outline
            pen = QPen(QColor(120, 120, 120), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawRect(rect)

        # -----------------------------
        # Live-drawing preview for polygon
        # -----------------------------
        if self.drawing_poly and self.mode == "poly":
            pts = [QPointF(x, y) for (x, y) in self.current_poly]
            if hasattr(self, "_mouse_pos"):
                pts.append(QPointF(*self._mouse_pos))

            if pts:
                # Dashed polyline
                pen = QPen(QColor(120, 120, 120), 2, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6.0, 6.0])
                pen.setDashOffset(self.dash_offset)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for i in range(len(pts) - 1):
                    painter.drawLine(pts[i], pts[i + 1])

                # Draw small points for user feedback
                for p in pts:
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.drawEllipse(p, 3, 3)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PySide6 + libVLC – Video with Interactive Shapes")
        self.resize(1280, 720)
        # Start maximized (not fullscreen)
        self.showMaximized()

        # VLC instance and player
        self.vlc_instance = vlc.Instance()
        self.mediaplayer = self.vlc_instance.media_player_new()

        # Central widget: container with video widget and overlay stacked
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)

        # video frame
        self.video_frame = VideoFrameWidget(self)
        self.video_frame.setStyleSheet("background-color: black;")
        lay.addWidget(self.video_frame)

        # overlay sits on top of video_frame
        # overlay as sibling, parent=central widget
        self.overlay = OverlayWidget(central)
        self.overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.overlay.raise_()  # bring on top
        self.overlay.show()

        # install event filter on video_frame to track resize
        self.video_frame.installEventFilter(self)

        # toolbar with QAction controls
        toolbar = QToolBar("Controls")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self.action_open = QAction("Open", self)
        self.action_open.triggered.connect(self.open_video_dialog)
        toolbar.addAction(self.action_open)

        self.action_play = QAction("Play", self)
        self.action_play.triggered.connect(self.play_pause)
        toolbar.addAction(self.action_play)

        self.action_stop = QAction("Stop", self)
        self.action_stop.triggered.connect(self.stop)
        toolbar.addAction(self.action_stop)

        toolbar.addSeparator()
        # drawing mode actions
        self.action_mode_box = QAction("Box Mode", self)
        self.action_mode_box.setCheckable(True)
        self.action_mode_box.setChecked(True)
        self.action_mode_box.triggered.connect(
            lambda: self.set_draw_mode("box"))
        toolbar.addAction(self.action_mode_box)

        self.action_mode_poly = QAction("Polygon Mode", self)
        self.action_mode_poly.setCheckable(True)
        self.action_mode_poly.triggered.connect(
            lambda: self.set_draw_mode("poly"))
        toolbar.addAction(self.action_mode_poly)

        toolbar.addSeparator()
        self.action_clear = QAction("Clear Shapes", self)
        self.action_clear.triggered.connect(self.overlay.clear_shapes)
        toolbar.addAction(self.action_clear)

        self.action_save = QAction("Save COCO", self)
        self.action_save.triggered.connect(self.save_coco)
        toolbar.addAction(self.action_save)

        # status bar showing current file path
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.path_label = QLabel("No file")
        self.status.addWidget(self.path_label)

        # timer to update VLC time or UI if needed
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(200)
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start()

        # current file info
        self.current_video_path = None
        self.current_video_size = (0, 0)  # width, height (approx from widget)

        # ensure overlay covers video frame area
        self.video_frame.installEventFilter(self)

        # set up VLC video output to the video_frame widget
        self._attach_vlc_output()

    def eventFilter(self, obj, ev):
        if obj is self.video_frame and ev.type() == QEvent.Type.Resize:
            # move overlay to cover video_frame
            geo = self.video_frame.geometry()
            self.overlay.setGeometry(geo)
        return super().eventFilter(obj, ev)

    def resizeEvent(self, event):
        pass

    def _attach_vlc_output(self):
        # IMPORTANT: cross-platform attach snippet using os.path.join etc.
        # Attach VLC video output to this widget’s window id
        # NOTE: on macOS, set_nsobject expects an NSView pointer; passing int(winId()) works for python-vlc in many setups.
        if sys.platform.startswith("darwin"):
            try:
                self.mediaplayer.set_nsobject(int(self.video_frame.winId()))
            except Exception as e:
                print("set_nsobject failed:", e)
        elif sys.platform.startswith("win"):
            try:
                self.mediaplayer.set_hwnd(int(self.video_frame.winId()))
            except Exception as e:
                print("set_hwnd failed:", e)
        else:  # Linux
            try:
                self.mediaplayer.set_xwindow(int(self.video_frame.winId()))
            except Exception as e:
                print("set_xwindow failed:", e)

    def open_video_dialog(self):
        # default folder ~/Thyra/video
        start_dir = THYRA_VIDEO_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Open video", start_dir,
                                              "Video files (*.mov *.mp4 *.mkv *.avi *.webm);;All files (*)")
        if path:
            self.open_video(path)

    def open_video(self, path: str):
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.current_video_path = path
        self.path_label.setText(path)
        # create media and play
        media = self.vlc_instance.media_new(path)
        self.mediaplayer.set_media(media)
        # re-attach output in case something changed
        self._attach_vlc_output()
        # play asynchronously
        self.mediaplayer.play()

    def play_pause(self):
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.action_play.setText("Play")
        else:
            self.mediaplayer.play()
            self.action_play.setText("Pause")

    def stop(self):
        self.mediaplayer.stop()
        self.action_play.setText("Play")

    def set_draw_mode(self, mode: str):
        self.overlay.set_mode(mode)
        if mode == "box":
            self.action_mode_box.setChecked(True)
            self.action_mode_poly.setChecked(False)
        else:
            self.action_mode_box.setChecked(False)
            self.action_mode_poly.setChecked(True)

    def _update_ui(self):
        # Intentionally minimal: could update time, slider, etc.
        pass

    def save_coco(self):
        """Dump current shapes for the opened video into a COCO-like JSON file in ~/Thyra/"""
        if not self.current_video_path:
            self.status.showMessage("No video open", 3000)
            return

        # get visible canvas size (widget size)
        canvas_w = self.overlay.width()
        canvas_h = self.overlay.height()

        # build COCO structure
        images = []
        annotations = []
        categories = [{"id": 1, "name": "shape", "supercategory": "shape"}]

        # image entry
        image_id = 1
        image_name = os.path.basename(self.current_video_path)
        images.append({
            "id": image_id,
            "file_name": image_name,
            "width": canvas_w,
            "height": canvas_h
        })

        ann_id = 1
        # bounding boxes
        for b in self.overlay.boxes:
            bbox = b.to_coco_bbox()
            area = bbox[2] * bbox[3]
            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": 1,
                "segmentation": [b.to_polygon()],
                "bbox": bbox,
                "area": area,
                "iscrowd": 0
            })
            ann_id += 1

        # polygons
        for p in self.overlay.polygons:
            segmentation = p.to_coco_segmentation()
            # compute bbox and area (simple bbox)
            xs = [pt[0] for pt in p.points]
            ys = [pt[1] for pt in p.points]
            if not xs or not ys:
                continue
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
            # area (polygon area via shoelace)
            area = abs(self._polygon_area(p.points))
            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": 1,
                "segmentation": segmentation,
                "bbox": bbox,
                "area": area,
                "iscrowd": 0
            })
            ann_id += 1

        coco = {
            "images": images,
            "annotations": annotations,
            "categories": categories
        }

        # Save file under ~/Thyra/<video_basename>.json
        basename = os.path.splitext(os.path.basename(self.current_video_path))[
            0]
        out_path = os.path.join(THYRA_DIR, f"{basename}_shapes_coco.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(coco, f, indent=2)
            self.status.showMessage(f"Saved COCO: {out_path}", 4000)
        except Exception as e:
            self.status.showMessage(f"Failed to save: {e}", 4000)

    @staticmethod
    def _polygon_area(points: List[Tuple[float, float]]) -> float:
        """Shoelace formula"""
        if len(points) < 3:
            return 0.0
        area = 0.0
        n = len(points)
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return area / 2.0


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
