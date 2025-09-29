#!/usr/bin/env python3
"""
PySide6 app with QOpenGLWidget video and image display + interactive overlay.

Features:
- Open video (hardware-accelerated with VLC) or images
- Draw bounding boxes and polygons
- Dashed outline animation
- Save shapes to COCO JSON
"""

import sys
import os
import json
from typing import List, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QToolBar, QLabel,
    QStatusBar, QVBoxLayout, QWidget
)
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QAction, QImage

import vlc

from app.ui.overlay_widget import OverlayWidget
from app.ui.video_widget import VideoWidget

HOME = os.path.expanduser("~")
THYRA_DIR = os.path.join(HOME, "Thyra")
THYRA_VIDEO_DIR = os.path.join(THYRA_DIR, "video")
THYRA_IMAGE_DIR = os.path.join(THYRA_DIR, "img")
os.makedirs(THYRA_VIDEO_DIR, exist_ok=True)
os.makedirs(THYRA_IMAGE_DIR, exist_ok=True)


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("PySide6 + OpenGL Video/Image + Overlay")
        self.showMaximized()

        # VLC
        self.vlc_instance = vlc.Instance("--vout=gl")
        self.mediaplayer = self.vlc_instance.media_player_new()

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)

        # Video/Image widget
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

        self.current_file_path: str | None = None
        self.current_file_type: str | None = None  # 'video' or 'image'

        # VLC output attach
        self._attach_vlc_output()

        # poll worker responses
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.poll_workers)
        self.poll_timer.start()

    # -----------------------------
    # Toolbar
    # -----------------------------
    def _setup_toolbar(self, toolbar):
        # Open video
        self.action_open_video = QAction("Open Video")
        self.action_open_video.triggered.connect(self.open_video_dialog)
        toolbar.addAction(self.action_open_video)

        # Open image
        self.action_open_image = QAction("Open Image")
        self.action_open_image.triggered.connect(self.open_image_dialog)
        toolbar.addAction(self.action_open_image)

        toolbar.addSeparator()

        # Video control
        self.action_play = QAction("Play")
        self.action_play.triggered.connect(self.play_pause)
        toolbar.addAction(self.action_play)

        self.action_stop = QAction("Stop")
        self.action_stop.triggered.connect(self.stop)
        toolbar.addAction(self.action_stop)

        toolbar.addSeparator()

        # Drawing mode
        self.action_mode_box = QAction("Box Mode")
        self.action_mode_box.setCheckable(True)
        self.action_mode_box.setChecked(True)
        self.action_mode_box.triggered.connect(lambda: self.set_draw_mode("box"))
        toolbar.addAction(self.action_mode_box)

        self.action_mode_poly = QAction("Polygon Mode")
        self.action_mode_poly.setCheckable(True)
        self.action_mode_poly.triggered.connect(lambda: self.set_draw_mode("poly"))
        toolbar.addAction(self.action_mode_poly)

        toolbar.addSeparator()

        # Overlay actions
        self.action_clear = QAction("Clear Shapes")
        self.action_clear.triggered.connect(self.overlay.clear_shapes)
        toolbar.addAction(self.action_clear)

        self.action_save = QAction("Save COCO")
        self.action_save.triggered.connect(self.save_coco)
        toolbar.addAction(self.action_save)

    # -----------------------------
    # Event filter
    # -----------------------------
    def eventFilter(self, obj, ev):
        if obj is self.video_widget and ev.type() == QEvent.Type.Resize:
            self.overlay.setGeometry(self.video_widget.geometry())
        return super().eventFilter(obj, ev)

    # -----------------------------
    # VLC output
    # -----------------------------
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

    # -----------------------------
    # Open video/image
    # -----------------------------
    def open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open video", THYRA_VIDEO_DIR,
                                              "Video files (*.mov *.mp4 *.mkv *.avi *.webm);;All files (*)")
        if path:
            self.open_video(path)

    def open_video(self, path: str):
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.current_file_path = path
        self.current_file_type = "video"
        self.path_label.setText(path)
        self.video_widget.image = None  # clear previous image

        media = self.vlc_instance.media_new(path)
        self.mediaplayer.set_media(media)
        self._attach_vlc_output()
        self.action_play.setText("Pause")
        self.mediaplayer.play()

    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image", THYRA_IMAGE_DIR,
                                              "Image files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif);;All files (*)")
        if path:
            self.open_image(path)

    def open_image(self, path: str):
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.current_file_path = path
        self.current_file_type = "image"
        self.path_label.setText(path)
        self.mediaplayer.stop()
        self.action_play.setText("Play")
        img = QImage(path)
        if img.isNull():
            self.status.showMessage("Failed to load image", 3000)
            return
        self.video_widget.image = img
        self.video_widget.update()

    # -----------------------------
    # Video controls
    # -----------------------------
    def play_pause(self):
        if self.current_file_type != "video":
            return
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.action_play.setText("Play")
        else:
            self.mediaplayer.play()
            self.action_play.setText("Pause")

    def stop(self):
        if self.current_file_type != "video":
            return
        self.mediaplayer.stop()
        self.action_play.setText("Play")

    # -----------------------------
    # Drawing
    # -----------------------------
    def set_draw_mode(self, mode: str):
        self.overlay.set_mode(mode)
        self.action_mode_box.setChecked(mode=="box")
        self.action_mode_poly.setChecked(mode=="poly")

    # -----------------------------
    # Save COCO
    # -----------------------------
    def save_coco(self):
        if not self.current_file_path:
            self.status.showMessage("No file open", 3000)
            return

        canvas_w = self.overlay.width()
        canvas_h = self.overlay.height()

        images = [{"id": 1, "file_name": os.path.basename(self.current_file_path),
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
        basename = os.path.splitext(os.path.basename(self.current_file_path))[0]
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

    def poll_workers(self):
        # poll for responses from worker processes
        try:
            while not self.app.res_q.empty():
                msg = self.app.res_q.get_nowait()
                # handle segment stub
                if msg.get('mask') is not None:
                    #self.canvas.apply_mask(msg['mask'])
                    self.status.showMessage('Mask received (stub)')
                if msg.get('count') is not None:
                    self.status.showMessage(
                        f"Density count (stub): {msg['count']}")
        except Exception:
            pass
# def main():
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.show()
#     sys.exit(app.exec())
#
#
# if __name__=="__main__":
#     main()