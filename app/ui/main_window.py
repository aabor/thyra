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
    QMainWindow, QFileDialog, QToolBar, QLabel,
    QStatusBar, QVBoxLayout, QWidget, QStyle
)
from PySide6.QtCore import Qt, QEvent, QTimer, QSize
from PySide6.QtGui import QAction, QImage, QIcon

import vlc

from app.ui.overlay_widget import OverlayWidget
from app.ui.video_widget import VideoWidget
from configuration import ICO_DIR, THYRA_DIR, THYRA_VIDEO_DIR, THYRA_IMAGE_DIR
from thyra_document import ThyraSettings, ThyraDocument

os.makedirs(THYRA_VIDEO_DIR, exist_ok=True)
os.makedirs(THYRA_IMAGE_DIR, exist_ok=True)


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.document: ThyraDocument = ThyraDocument()
        self.settings: ThyraSettings = ThyraSettings()
        self.icon_pause = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPause)
        self.icon_play = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPlay)
        self.app = app
        self.setWindowTitle("PySide6 + OpenGL Video/Image + Overlay")
        self.showMaximized()

        self.load_settings()

        # VLC
        self.vlc_instance = vlc.Instance("--vout=gl")
        self.mediaplayer = self.vlc_instance.media_player_new()

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video/Image widget
        self.video_widget = VideoWidget(self)
        layout.addWidget(self.video_widget)

        # Overlay
        self.overlay = OverlayWidget(central)
        self.overlay.main_window = self
        self.overlay.setGeometry(self.video_widget.geometry())
        self.overlay.raise_()
        self.overlay.show()

        # Event filter to resize overlay
        self.video_widget.installEventFilter(self)

        # Toolbar
        toolbar = QToolBar("Controls")
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._setup_toolbar(toolbar)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.path_label = QLabel("No file")
        self.status.addWidget(self.path_label)

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
        # Create document
        self.action_create_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'document--pencil.png')),
            "Create", self)
        toolbar.addAction(self.action_create_document)
        self.action_create_document.triggered.connect(
            self.create_document_dialog)
        # Open document
        self.action_open_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'folder-horizontal-open.png')),
            "Create", self)
        toolbar.addAction(self.action_open_document)
        self.action_open_document.triggered.connect(
            self.open_document_dialog)
        # Duplicate document
        self.action_duplicate_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'document-copy.png')),
            "Duplicate", self)
        toolbar.addAction(self.action_duplicate_document)
        self.action_duplicate_document.triggered.connect(
            self.duplicate_document)
        # Export document to COCO JSON
        self.action_export_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'document-export.png')),
            "Export COCO", self)
        toolbar.addAction(self.action_export_document)
        self.action_export_document.triggered.connect(
            self.save_coco)

        # Open video
        self.action_open_video = QAction(
            QIcon(os.path.join(ICO_DIR, 'folder-open-film.png')),
            "Open video", self)
        self.action_open_video.triggered.connect(self.open_video_dialog)
        toolbar.addAction(self.action_open_video)

        # Open image
        self.action_open_image = QAction(
            QIcon(os.path.join(ICO_DIR, 'folder-open-image.png')),
            "Open image", self)
        self.action_open_image.triggered.connect(self.open_image_dialog)
        toolbar.addAction(self.action_open_image)

        toolbar.addSeparator()

        # Video control
        self.action_play = QAction(self.icon_play, "Play", self)
        self.action_play.triggered.connect(self.play_pause)
        toolbar.addAction(self.action_play)

        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop)
        self.action_stop = QAction(icon, "Stop")
        self.action_stop.triggered.connect(self.stop)
        toolbar.addAction(self.action_stop)

        toolbar.addSeparator()

        # Drawing mode
        self.action_mode_box = QAction(
            QIcon(os.path.join(ICO_DIR, 'layer-shape.png')),
            "Box mode", self)
        self.action_mode_box.setCheckable(True)
        self.action_mode_box.setChecked(True)
        self.action_mode_box.triggered.connect(
            lambda: self.set_draw_mode("box"))
        toolbar.addAction(self.action_mode_box)

        self.action_mode_poly = QAction(
            QIcon(os.path.join(ICO_DIR, 'layer-shape-polygon.png')),
            "Polygon mode", self)
        self.action_mode_poly.setCheckable(True)
        self.action_mode_poly.triggered.connect(
            lambda: self.set_draw_mode("poly"))
        toolbar.addAction(self.action_mode_poly)

        toolbar.addSeparator()

        self.action_redo = QAction(
            QIcon(os.path.join(ICO_DIR, 'eraser--plus.png')),
            "Redo", self)
        self.action_redo.triggered.connect(self.overlay.redo)
        toolbar.addAction(self.action_redo)

        self.action_undo = QAction(
            QIcon(os.path.join(ICO_DIR, 'eraser--minus.png')),
            "Undo", self)
        self.action_undo.triggered.connect(self.overlay.undo)
        toolbar.addAction(self.action_undo)

        # Overlay actions
        self.action_clear = QAction(
            QIcon(os.path.join(ICO_DIR, 'ui-text-field-clear-button.png')),
            "Clear shapes", self)
        self.action_clear.triggered.connect(self.overlay.clear_shapes)
        toolbar.addAction(self.action_clear)

    def load_settings(self):
        """Load settings.json from THYRA_DIR. Create this file if missing.
        class ThyraSettings contains settings of Thyra app"""
        self.settings = ThyraSettings()
        pass

    # -----------------------------
    # Documents
    # -----------------------------
    def create_document_dialog(self):
        """class ThyraDocument contains supported fields of the document.
        Convention on file names: automatically generated file
        name has format YYYYmmdd_HHMMSS.json, use current time value.
        Document is a nested dictionary. Contains relative path to selected
        image or video relative to THYRA_DIR. Document also contains masks
        introduced by the user. Masks have relative coordinates in the range [0,
        1]. When drawing masks relative coordinates must be converted to
        screen coordinates. Ensure correct screen coordinates in case of
        image resize at runtime. Always save documents in COCO json format."""
        self.document = ThyraDocument()
        pass

    def open_document_dialog(self):
        """Application must try to open the most recent document at start.
        The settings.json file must contain a reference to the most recent
        document"""
        pass

    def duplicate_document(self):
        """Save current document and create a new file with a new name and
        the same content. Convention on file names: automtically generated file
        name has format YYYYmmdd_HHMMSS.json, use current time value."""
        pass

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
        path, _ = QFileDialog.getOpenFileName(self, "Open video",
                                              THYRA_VIDEO_DIR,
                                              "Video files (*.mov *.mp4 *.mkv *.avi *.webm);;All files (*)")
        if path:
            self.open_video(path)

    def open_video(self, path: str):
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.document.src_file_path = path
        self.document.src_file_type = "video"
        self.path_label.setText(path)
        self.video_widget.image = None  # clear previous image

        media = self.vlc_instance.media_new(path)
        self.mediaplayer.set_media(media)
        self._attach_vlc_output()
        self.action_play.setText("Pause")
        self.mediaplayer.play()

    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image",
                                              THYRA_IMAGE_DIR,
                                              "Image files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif);;All files (*)")
        if path:
            self.open_image(path)

    def open_image(self, path: str):
        if not os.path.exists(path):
            self.status.showMessage("File not found", 3000)
            return
        self.document.src_file_path = path
        self.document.src_file_type = "image"
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
        if self.document.src_file_type != "video":
            return
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.action_play.setIcon(self.icon_play)
            self.action_play.setText("Play")
        else:
            self.mediaplayer.play()
            self.action_play.setIcon(self.icon_pause)
            self.action_play.setText("Pause")

    def stop(self):
        if self.document.src_file_type != "video":
            return
        self.mediaplayer.stop()
        self.action_play.setText("Play")

    # -----------------------------
    # Drawing
    # -----------------------------
    def set_draw_mode(self, mode: str):
        self.overlay.set_mode(mode)
        self.action_mode_box.setChecked(mode == "box")
        self.action_mode_poly.setChecked(mode == "poly")

    # -----------------------------
    # Save COCO
    # -----------------------------
    def save_coco(self):
        if not self.document.src_file_path:
            self.status.showMessage("No file open", 3000)
            return

        canvas_w = self.overlay.width()
        canvas_h = self.overlay.height()

        images = [
            {"id": 1, "file_name": os.path.basename(
                self.document.src_file_path),
             "width": canvas_w, "height": canvas_h}]
        annotations = []
        categories = [{"id": 1, "name": "shape", "supercategory": "shape"}]
        ann_id = 1

        for _, b in self.document.boxes:
            bbox = b.to_coco_bbox()
            area = bbox[2] * bbox[3]
            annotations.append({"id": ann_id, "image_id": 1, "category_id": 1,
                                "segmentation": [b.to_polygon()],
                                "bbox": bbox, "area": area, "iscrowd": 0})
            ann_id += 1

        for _, p in self.document.polygons:
            segmentation = p.to_coco_segmentation()
            xs = [pt[0] for pt in p.points]
            ys = [pt[1] for pt in p.points]
            if not xs or not ys:
                continue
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
            area = abs(self._polygon_area(p.points))
            annotations.append({"id": ann_id, "image_id": 1, "category_id": 1,
                                "segmentation": segmentation, "bbox": bbox,
                                "area": area, "iscrowd": 0})
            ann_id += 1

        coco = {"images": images, "annotations": annotations,
                "categories": categories}
        try:
            with open(self.document.src_file_path, "w", encoding="utf-8") as f:
                json.dump(coco, f, indent=2)
            self.status.showMessage(f"Saved COCO: {self.document.src_file_path}", 4000)
        except Exception as e:
            self.status.showMessage(f"Failed to save: {e}", 4000)

    @staticmethod
    def _polygon_area(points: List[Tuple[float, float]]) -> float:
        n = len(points)
        if n < 3: return 0
        area = 0
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return area / 2.0

    def poll_workers(self):
        # poll for responses from worker processes
        try:
            while not self.app.res_q.empty():
                msg = self.app.res_q.get_nowait()
                # handle segment stub
                if msg.get('mask') is not None:
                    # self.canvas.apply_mask(msg['mask'])
                    self.status.showMessage('Mask received (stub)')
                if msg.get('count') is not None:
                    self.status.showMessage(
                        f"Density count (stub): {msg['count']}")
        except Exception:
            pass

