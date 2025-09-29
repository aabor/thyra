#!/usr/bin/env python3
"""
PySide6 app with QOpenGLWidget video playback (hardware-accelerated) and interactive overlay.

Features:
- 4K+ hardware-accelerated video using OpenGL
- Draw bounding boxes and polygons with transparent fill
- Dashed grey outline animation (CCW)
- Save shapes to COCO JSON
"""

import sys
import os
import json
import uuid
from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QToolBar, QLabel, QStatusBar, QVBoxLayout, QWidget
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QAction, QPolygonF

from PySide6.QtOpenGLWidgets import QOpenGLWidget

import vlc

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
        flattened = []
        for x, y in self.points:
            flattened.extend([x, y])
        return [flattened]


class VideoWidget(QOpenGLWidget):
    """QOpenGLWidget used for hardware-accelerated video output."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAutoFillBackground(False)


class OverlayWidget(QWidget):
    """Transparent overlay for drawing boxes and polygons."""
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

        self.dash_offset = 0.0
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(30)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

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
            else:
                if not self.drawing_poly:
                    self.drawing_poly = True
                    self.current_poly = []
                self.current_poly.append((event.position().x(), event.position().y()))
        self.update()

    def mouseMoveEvent(self, event):
        if self.drawing_box:
            self.box_current = event.position()
        elif self.drawing_poly:
            self._mouse_pos = (event.position().x(), event.position().y())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_box and \
            self.mode == "box":
            self.drawing_box = False
            p1, p2 = self.box_start, self.box_current
            x, y = min(p1.x(), p2.x()), min(p1.y(), p2.y())
            w, h = abs(p2.x() - p1.x()), abs(p2.y() - p1.y())
            if w > 5 and h > 5:
                self.boxes.append(BoundingBox(x, y, w, h, str(uuid.uuid4())))
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.mode == "poly" and self.drawing_poly and len(self.current_poly) >= 3:
            self.polygons.append(PolygonShape(list(self.current_poly), str(uuid.uuid4())))
            self.drawing_poly = False
            self.current_poly = []
        self.update()

    def keyPressEvent(self, event):
        if self.mode == "poly" and self.drawing_poly and event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if len(self.current_poly) >= 3:
                self.polygons.append(PolygonShape(list(self.current_poly), str(uuid.uuid4())))
            self.drawing_poly = False
            self.current_poly = []
        self.update()

    def _on_anim_tick(self):
        self.dash_offset -= 1.5
        if self.dash_offset < -1000:
            self.dash_offset = 0
        self.update()

    def clear_shapes(self):
        self.boxes = []
        self.polygons = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # -----------------------------
        # Draw existing polygons (only outline)
        # -----------------------------
        for poly in self.polygons:
            if len(poly.points) < 3:
                continue
            qpoints = [QPointF(x, y) for (x, y) in poly.points]

            # Draw dashed outline
            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([6.0, 6.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            polygon = QPolygonF(qpoints)
            painter.drawPolygon(polygon)  # Closed polygon

        # -----------------------------
        # Draw existing bounding boxes (only outline)
        # -----------------------------
        for box in self.boxes:
            rect = QRectF(box.x, box.y, box.w, box.h)

            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # -----------------------------
        # Live-drawing preview for box (only outline)
        # -----------------------------
        if self.drawing_box and self.mode == "box":
            p1, p2 = self.box_start, self.box_current
            rect = QRectF(min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                          abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))

            pen = QPen(QColor(120, 120, 120), 2, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([8.0, 4.0])
            pen.setDashOffset(self.dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # -----------------------------
        # Live-drawing preview for polygon (open shape)
        # -----------------------------
        if self.drawing_poly and self.current_poly:
            pts = [QPointF(x, y) for (x, y) in self.current_poly]
            if hasattr(self, "_mouse_pos"):
                pts.append(QPointF(*self._mouse_pos))

            if len(pts) >= 2:
                pen = QPen(QColor(120, 120, 120), 2, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6.0, 6.0])
                pen.setDashOffset(self.dash_offset)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                polyline = QPolygonF(pts)
                painter.drawPolyline(polyline)

            # Draw small feedback points
            for p in pts:
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(p, 3, 3)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 + OpenGL Video + Overlay")
        self.resize(1280,720)
        self.showMaximized()

        # VLC
        self.vlc_instance = vlc.Instance("--vout=gl")
        self.mediaplayer = self.vlc_instance.media_player_new()

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)

        # Video widget
        self.video_widget = VideoWidget(self)
        layout.addWidget(self.video_widget)

        # Overlay
        self.overlay = OverlayWidget(central)
        self.overlay.setGeometry(self.video_widget.geometry())
        self.overlay.raise_()
        self.overlay.show()

        # Event filter to resize overlay
        self.video_widget.installEventFilter(self)

        # Toolbar
        toolbar = QToolBar("Controls")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._setup_toolbar(toolbar)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.path_label = QLabel("No file")
        self.status.addWidget(self.path_label)

        self.current_video_path = None

        # VLC output attach
        self._attach_vlc_output()

    def _setup_toolbar(self, toolbar):
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

        self.action_mode_box = QAction("Box Mode", self)
        self.action_mode_box.setCheckable(True)
        self.action_mode_box.setChecked(True)
        self.action_mode_box.triggered.connect(lambda: self.set_draw_mode("box"))
        toolbar.addAction(self.action_mode_box)

        self.action_mode_poly = QAction("Polygon Mode", self)
        self.action_mode_poly.setCheckable(True)
        self.action_mode_poly.triggered.connect(lambda: self.set_draw_mode("poly"))
        toolbar.addAction(self.action_mode_poly)

        toolbar.addSeparator()
        self.action_clear = QAction("Clear Shapes", self)
        self.action_clear.triggered.connect(self.overlay.clear_shapes)
        toolbar.addAction(self.action_clear)

        self.action_save = QAction("Save COCO", self)
        self.action_save.triggered.connect(self.save_coco)
        toolbar.addAction(self.action_save)

    def eventFilter(self, obj, ev):
        if obj is self.video_widget and ev.type() == QEvent.Type.Resize:
            self.overlay.setGeometry(self.video_widget.geometry())
        return super().eventFilter(obj, ev)

    def _attach_vlc_output(self):
        if sys.platform.startswith("darwin"):
            try:
                self.mediaplayer.set_nsobject(int(self.video_widget.winId()))
            except Exception as e:
                print("set_nsobject failed:", e)
        elif sys.platform.startswith("win"):
            try:
                self.mediaplayer.set_hwnd(int(self.video_widget.winId()))
            except Exception as e:
                print("set_hwnd failed:", e)
        else:
            try:
                self.mediaplayer.set_xwindow(int(self.video_widget.winId()))
            except Exception as e:
                print("set_xwindow failed:", e)

    def open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open video", THYRA_VIDEO_DIR,
                                              "Video files (*.mov *.mp4 *.mkv *.avi *.webm);;All files (*)")
        if path:
            self.open_video(path)

    def open_video(self, path: str):
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.current_video_path = path
        self.path_label.setText(path)
        media = self.vlc_instance.media_new(path)
        self.mediaplayer.set_media(media)
        self._attach_vlc_output()
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
        self.action_mode_box.setChecked(mode=="box")
        self.action_mode_poly.setChecked(mode=="poly")

    def save_coco(self):
        if not self.current_video_path:
            self.status.showMessage("No video open", 3000)
            return

        canvas_w = self.overlay.width()
        canvas_h = self.overlay.height()

        images = [{"id": 1, "file_name": os.path.basename(self.current_video_path),
                   "width": canvas_w, "height": canvas_h}]
        annotations = []
        categories = [{"id":1, "name":"shape","supercategory":"shape"}]
        ann_id = 1

        for b in self.overlay.boxes:
            bbox = b.to_coco_bbox()
            area = bbox[2]*bbox[3]
            annotations.append({"id":ann_id,"image_id":1,"category_id":1,
                                "segmentation":[b.to_polygon()],
                                "bbox":bbox,"area":area,"iscrowd":0})
            ann_id += 1

        for p in self.overlay.polygons:
            segmentation = p.to_coco_segmentation()
            xs = [pt[0] for pt in p.points]
            ys = [pt[1] for pt in p.points]
            if not xs or not ys:
                continue
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            bbox = [x_min, y_min, x_max-x_min, y_max-y_min]
            area = abs(self._polygon_area(p.points))
            annotations.append({"id":ann_id,"image_id":1,"category_id":1,
                                "segmentation":segmentation,"bbox":bbox,
                                "area":area,"iscrowd":0})
            ann_id += 1

        coco = {"images":images,"annotations":annotations,"categories":categories}
        basename = os.path.splitext(os.path.basename(self.current_video_path))[0]
        out_path = os.path.join(THYRA_DIR, f"{basename}_shapes_coco.json")
        try:
            with open(out_path,"w",encoding="utf-8") as f:
                json.dump(coco,f,indent=2)
            self.status.showMessage(f"Saved COCO: {out_path}",4000)
        except Exception as e:
            self.status.showMessage(f"Failed to save: {e}",4000)

    @staticmethod
    def _polygon_area(points:List[Tuple[float,float]])->float:
        n=len(points)
        if n<3: return 0
        area=0
        for i in range(n):
            x1,y1=points[i]
            x2,y2=points[(i+1)%n]
            area += x1*y2 - x2*y1
        return area/2.0


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()