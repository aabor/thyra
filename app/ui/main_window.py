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
from datetime import datetime
from typing import List, Tuple
import logging

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QToolBar, QLabel,
    QStatusBar, QVBoxLayout, QWidget, QStyle
)
from PySide6.QtCore import Qt, QEvent, QTimer, QSize
from PySide6.QtGui import QAction, QImage, QIcon

import vlc

from app.ui.overlay_widget import OverlayWidget
from app.ui.vector_masks import BoundingBox, PolygonShape
from app.ui.video_widget import VideoWidget
from configuration import ICO_DIR, THYRA_DIR, THYRA_VIDEO_DIR, THYRA_IMAGE_DIR, \
    LOGGER_NAME
from thyra_document import ThyraDocument
from thyra_settings import ThyraSettings

logger = logging.getLogger(LOGGER_NAME)

os.makedirs(THYRA_VIDEO_DIR, exist_ok=True)
os.makedirs(THYRA_IMAGE_DIR, exist_ok=True)


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.image_height = None
        self.image_width = None
        self.current_document_file_path = ""
        self.document: ThyraDocument = ThyraDocument()
        self.settings: ThyraSettings = ThyraSettings()
        self.setWindowIcon(QIcon(os.path.join(ICO_DIR, "favicon.icns")))
        self.icon_pause = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPause)
        self.icon_play = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPlay)
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

        self.load_settings()
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
        # Save document
        self.action_save_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'disk-return-black.png')),
            "Save", self)
        toolbar.addAction(self.action_save_document)
        self.action_save_document.triggered.connect(
            self.save_document)
        # Export document to COCO JSON
        self.action_export_document = QAction(
            QIcon(os.path.join(ICO_DIR, 'document-export.png')),
            "Export COCO", self)
        toolbar.addAction(self.action_export_document)
        self.action_export_document.triggered.connect(
            self.export_to_coco)

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
        settings_path = os.path.join(THYRA_DIR, "settings.json")
        try:
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # defensive: only set fields we know about
                if isinstance(data,
                              dict) and "most_recent_document_path" in data:
                    self.settings = ThyraSettings(
                        most_recent_document_path=data.get(
                            "most_recent_document_path", "")
                    )
                # attempt to open most recent document if exists
                mr = getattr(self.settings, "most_recent_document_path", "")
                if mr:
                    mr_abs = mr if os.path.isabs(mr) else os.path.join(
                        THYRA_DIR, mr)
                    if os.path.exists(mr_abs):
                        # try to open silently (don't show dialog)
                        self.load_document(mr_abs)
                        self.current_document_file_path = mr_abs
            else:
                # create default settings file
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(self.settings.__dict__, f, indent=2)
        except Exception as e:
            # don't crash the app for settings load errors
            logger.error(f"load_settings error: {e}")

    def _save_settings(self):
        try:
            settings_path = os.path.join(THYRA_DIR, "settings.json")
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings.__dict__, f, indent=2)
        except Exception as e:
            logger.error(f"save_settings error: {e}")

    def create_document_dialog(self):
        """Create a new ThyraDocument and save it under THYRA_DIR. The user
        chooses an image or video file which will be referenced relatively
        inside the new document. The created document is saved as
        YYYYmmdd_HHMMSS.json inside THYRA_DIR and the settings are updated."""
        # Ask user to pick an image or video (both filters available)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose source image or video", THYRA_DIR,
            "Image or Video files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.mov *.mp4 *.mkv *.avi *.webm);;All files (*)"
        )
        if not path:
            return

        # determine src_file_type from extension
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mov", ".mp4", ".mkv", ".avi", ".webm"):
            src_type = "video"
        else:
            src_type = "image"

        # create document (store relative path where possible)
        rel_path = os.path.relpath(path, THYRA_DIR) if os.path.commonpath(
            [THYRA_DIR, path]) == THYRA_DIR else path
        self.document = ThyraDocument(src_file_path=rel_path,
                                      src_file_type=src_type,
                                      boxes=[], polygons=[])
        # save document to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{timestamp}.json"
        out_path = os.path.join(THYRA_DIR, fname)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                # dataclasses_json provides to_json but keep simple JSON structure
                json.dump(self.document.to_dict(), f, indent=2)
            # update settings and remember current document file path
            self.settings.most_recent_document_path = os.path.relpath(
                out_path, THYRA_DIR)
            self.current_document_file_path = out_path
            self._save_settings()
            self.status.showMessage(f"Created document: {out_path}", 4000)
            # open associated media immediately
            if src_type == "image":
                self.open_image(path)
            else:
                self.open_video(path)
        except Exception as e:
            msg = f"Failed to create document: {e}"
            self.status.showMessage(msg, 4000)
            logger.error(msg)

    def open_document_dialog(self):
        """Open a Thyra JSON document from disk (file dialog). Loaded shapes
        are converted from relative coordinates (if present) into absolute
        coordinates for the current canvas size so overlay can draw them."""
        path, _ = QFileDialog.getOpenFileName(self, "Open document", THYRA_DIR,
                                              "JSON document (*.json);;All files (*)")
        if not path:
            return
        self.load_document(path)
        # save this as most recent
        try:
            rel = os.path.relpath(path, THYRA_DIR)
        except Exception:
            rel = path
        self.settings.most_recent_document_path = rel
        self._save_settings()

    def load_document(self, path: str):
        """Load a saved document with normalized coordinates."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            msg = f"Failed to open document: {e}"
            self.status.showMessage(msg, 4000)
            logger.error(msg)
            return

        self.document = ThyraDocument.from_dict(data)
        self.current_document_file_path = path

        # try to open associated media file
        src = self.document.src_file_path
        if src:
            full_src = src if os.path.isabs(src) else os.path.join(
                THYRA_DIR, src)
            if os.path.exists(full_src):
                if self.document.src_file_type == "image":
                    self.open_image(full_src)
                elif self.document.src_file_type == "video":
                    self.open_video(full_src)
                else:
                    ext = os.path.splitext(full_src)[1].lower()
                    if ext in (".mov", ".mp4", ".mkv", ".avi", ".webm"):
                        self.open_video(full_src)
                    else:
                        self.open_image(full_src)

        self.overlay.update()
        msg = f"Opened document {path}"
        self.status.showMessage(msg, 3000)
        logger.info(msg)

    def save_document(self):
        """Save current document. Coordinates are already normalized to image size."""
        if not self.current_document_file_path:
            msg = "No file open"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        try:
            with open(self.current_document_file_path, "w",
                      encoding="utf-8") as f:
                data = self.document.to_dict()
                json.dump(data, f, indent=2)
            msg = f"Saved: {self.current_document_file_path}"
            self.status.showMessage(msg, 4000)
            logger.info(msg)
        except Exception as e:
            msg = f"Failed to save: {e}"
            self.status.showMessage(msg, 4000)
            logger.error(msg)

    def duplicate_document(self):
        """Save current document and create a new file with a new name and
        the same content. Convention: YYYYmmdd_HHMMSS.json"""
        if not self.current_document_file_path:
            return
        try:
            with open(self.current_document_file_path, "r",
                      encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            msg = f"Failed to read current document: {e}"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{timestamp}.json"
        out_path = os.path.join(THYRA_DIR, new_name)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.current_document_file_path = out_path
            self.settings.most_recent_document_path = os.path.relpath(
                out_path, THYRA_DIR)
            self._save_settings()
            msg = f"Duplicated document → {out_path}"
            self.status.showMessage(msg, 4000)
            logger.info(msg)
        except Exception as e:
            msg = f"Failed to duplicate document: {e}"
            self.status.showMessage(msg, 4000)
            logger.error(msg)

    # -----------------------------
    # Export to COCO JSON
    # -----------------------------
    def export_to_coco(self):
        if not self.current_document_file_path:
            msg = "No file opened"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        canvas_w = self.overlay.width()
        canvas_h = self.overlay.height()
        images = [
            {"id": 1,
             "file_name": self.document.src_file_path,
             "width": canvas_w, "height": canvas_h}
        ]
        annotations = []
        categories = [{"id": 1, "name": "shape", "supercategory": "shape"}]
        ann_id = 1

        # Boxes
        for _, b in self.document.boxes:
            bbox = b.to_coco_bbox()
            area = bbox[2] * bbox[3]
            annotations.append({
                "id": ann_id, "image_id": 1, "category_id": 1,
                "segmentation": [b.to_polygon()],
                "bbox": bbox, "area": area, "iscrowd": 0
            })
            ann_id += 1

        # Polygons
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
            annotations.append({
                "id": ann_id, "image_id": 1, "category_id": 1,
                "segmentation": segmentation, "bbox": bbox,
                "area": area, "iscrowd": 0
            })
            ann_id += 1

        coco = {
            "images": images,
            "annotations": annotations,
            "categories": categories
        }

        # Add _COCO suffix
        base, ext = os.path.splitext(self.current_document_file_path)
        out_file_path = f"{base}_COCO.json"

        try:
            with open(out_file_path, "w", encoding="utf-8") as f:
                json.dump(coco, f, indent=2)
            msg = f"Saved COCO JSON: {out_file_path}"
            self.status.showMessage(msg, 4000)
            logger.info(msg)
        except Exception as e:
            msg = f"Failed to save: {e}"
            self.status.showMessage(msg, 4000)
            logger.error(msg)

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
                logger.error(f"set_nsobject failed: {e}")
        elif sys.platform.startswith("win"):
            try:
                self.mediaplayer.set_hwnd(int(self.video_widget.winId()))
            except Exception as e:
                logger.error(f"set_hwnd failed: {e}")
        else:
            try:
                self.mediaplayer.set_xwindow(int(self.video_widget.winId()))
            except Exception as e:
                logger.error(f"set_xwindow failed: {e}")

    # -----------------------------
    # Open video/image
    # -----------------------------
    def open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open video",
            THYRA_VIDEO_DIR,
            "Video files (*.mov *.mp4 *.mkv *.avi *.webm);;All files (*)"
        )
        if path:
            self.open_video(path)

    def open_video(self, path: str):
        if not os.path.exists(path):
            msg = f"File not found {path}"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        self.document.src_file_path = path
        self.document.src_file_type = "video"
        self.path_label.setText(path)
        self.video_widget.image = None  # clear previous image

        media = self.vlc_instance.media_new(path)
        self.mediaplayer.set_media(media)
        self._attach_vlc_output()

        # Start playing briefly to allow VLC to detect video dimensions
        self.mediaplayer.play()

        # Poll until dimensions are available (non-blocking)
        timeout_ms = 3000
        interval_ms = 50
        elapsed = 0
        while elapsed < timeout_ms:
            width = self.mediaplayer.video_get_width()
            height = self.mediaplayer.video_get_height()
            if width > 0 and height > 0:
                self.image_width = width
                self.image_height = height
                logger.info(f"Loaded video {path} with size {width}x{height}")
                break
            QTimer.singleShot(interval_ms, lambda: None)  # allow event loop
            elapsed += interval_ms
        else:
            # fallback if dimensions cannot be read
            self.image_width = 1920
            self.image_height = 1080
            logger.warning(
                f"Could not determine video dimensions for {path}, using default 1920x1080")

        self.action_play.setText("Pause")

    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image",
            THYRA_IMAGE_DIR,
            "Image files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif);;All files (*)"
        )
        if path:
            self.open_image(path)

    def open_image(self, path: str):
        if not os.path.exists(path):
            msg = f"File not found {path}"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        self.document.src_file_path = path
        self.document.src_file_type = "image"
        self.path_label.setText(path)
        self.mediaplayer.stop()
        self.action_play.setText("Play")

        img = QImage(path)
        if img.isNull():
            msg = f"Failed to load image {path}"
            self.status.showMessage(msg, 3000)
            logger.error(msg)
            return

        self.video_widget.image = img
        self.video_widget.update()

        # Track image dimensions
        self.image_width = img.width()
        self.image_height = img.height()
        logger.info(
            f"Loaded image {path} with size {self.image_width}x{self.image_height}")

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
                    log_msg = 'Mask received (stub)'
                    logger.info(log_msg)
                    self.status.showMessage(log_msg)
                if msg.get('count') is not None:
                    log_msg = f"Density count (stub): {msg['count']}"
                    self.status.showMessage(log_msg)
                    logger.info(log_msg)
        except Exception as e:
            logger.error(f"Poll workers: {e}")
            pass
