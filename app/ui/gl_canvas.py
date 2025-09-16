from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer
from OpenGL.GL import *
import numpy as np
import cv2
from pathlib import Path
import time
import multiprocessing as mp
from multiprocessing import shared_memory


class GLCanvas(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)

        # Frame / image
        self.current_frame = None
        self.current_image_path = None
        self.tex_id = None
        self.tex_width = 0
        self.tex_height = 0

        # Mask overlay
        self.mask = None
        self.mask_tex = None
        self.mask_visible = True

        # Bounding box drawing
        self.drawing = False
        self.start_pos = None
        self.end_pos = None
        self.last_bbox = None

        # Video playback
        self.video_cap = None
        self.video_timer = None
        self.video_fps = 30
        self._video_start_time = None

        # Shared memory (async decoder placeholder)
        self._shm = None
        self._shm_size = 0
        self._shm_w = 0
        self._shm_h = 0
        self._decoder_proc = None
        self._decoder_frame_q = None
        self._decoder_ctrl_q = None

    # ------------------- OpenGL Lifecycle -------------------
    def initializeGL(self):
        glClearColor(0.12, 0.12, 0.12, 1.0)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.tex_id and self.current_frame is not None:
            self._draw_image_texture()
            if self.mask is not None and self.mask_visible:
                self._draw_mask_texture(alpha=0.45)
            if self.last_bbox is not None:
                self._draw_bbox(self.last_bbox)
            if self.drawing and self.start_pos and self.end_pos:
                temp_bbox = self._compute_temp_bbox()
                if temp_bbox:
                    self._draw_bbox(temp_bbox)

    # ------------------- Texture Management -------------------
    def _ensure_texture(self, w, h):
        if self.tex_id is None:
            self.tex_id = glGenTextures(1)
        if (w != self.tex_width) or (h != self.tex_height):
            self.tex_width = w
            self.tex_height = h
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB8, w, h, 0, GL_RGB,
                         GL_UNSIGNED_BYTE, None)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glBindTexture(GL_TEXTURE_2D, 0)

    def _ensure_mask_texture(self, w, h):
        if self.mask_tex is None:
            self.mask_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.mask_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, w, h, 0, GL_RED, GL_UNSIGNED_BYTE,
                     None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glBindTexture(GL_TEXTURE_2D, 0)

    def _upload_frame_to_texture(self, frame):
        h, w = frame.shape[:2]
        self._ensure_texture(w, h)
        frame_flip = np.ascontiguousarray(np.flipud(frame))
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE,
                        frame_flip)
        glBindTexture(GL_TEXTURE_2D, 0)

    def _upload_mask_to_texture(self, mask):
        h, w = mask.shape[:2]
        self._ensure_mask_texture(w, h)
        mask_flip = np.ascontiguousarray(np.flipud(mask))
        glBindTexture(GL_TEXTURE_2D, self.mask_tex)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RED, GL_UNSIGNED_BYTE,
                        mask_flip)
        glBindTexture(GL_TEXTURE_2D, 0)

    # ------------------- Drawing Helpers -------------------
    def _compute_aspect_fit(self, img_w, img_h, win_w, win_h):
        if img_w <= 0 or img_h <= 0:
            return 0, 0, win_w, win_h
        img_aspect = img_w / img_h
        win_aspect = win_w / win_h
        if img_aspect > win_aspect:
            w = win_w
            h = int(win_w / img_aspect)
            x = 0
            y = (win_h - h) // 2
        else:
            h = win_h
            w = int(win_h * img_aspect)
            x = (win_w - w) // 2
            y = 0
        return x, y, w, h

    def _draw_image_texture(self):
        glColor4f(1.0, 1.0, 1.0, 1.0)
        x, y, w, h = self._compute_aspect_fit(self.tex_width, self.tex_height,
                                              self.width(), self.height())
        left, right = 2 * x / self.width() - 1, 2 * (x + w) / self.width() - 1
        top, bottom = 1 - 2 * y / self.height(), 1 - 2 * (y + h) / self.height()
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0);
        glVertex2f(left, bottom)
        glTexCoord2f(1, 0);
        glVertex2f(right, bottom)
        glTexCoord2f(1, 1);
        glVertex2f(right, top)
        glTexCoord2f(0, 1);
        glVertex2f(left, top)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)

    def _draw_mask_texture(self, alpha=0.45):
        x, y, w, h = self._compute_aspect_fit(self._shm_w or self.tex_width,
                                              self._shm_h or self.tex_height,
                                              self.width(), self.height())
        left, right = 2 * x / self.width() - 1, 2 * (x + w) / self.width() - 1
        top, bottom = 1 - 2 * y / self.height(), 1 - 2 * (y + h) / self.height()
        glColor4f(1, 0.4, 0.2, alpha)
        glBindTexture(GL_TEXTURE_2D, self.mask_tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0);
        glVertex2f(left, bottom)
        glTexCoord2f(1, 0);
        glVertex2f(right, bottom)
        glTexCoord2f(1, 1);
        glVertex2f(right, top)
        glTexCoord2f(0, 1);
        glVertex2f(left, top)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)
        glColor4f(1.0, 1.0, 1.0, 1.0)

    def _draw_bbox(self, bbox):
        x0, y0, x1, y1 = bbox
        win_w, win_h = self.width(), self.height()
        ox, oy, w, h = self._compute_aspect_fit(self.tex_width, self.tex_height,
                                                win_w, win_h)
        sx, sy = w / self.tex_width, h / self.tex_height
        rx0, ry0 = ox + x0 * sx, oy + y0 * sy
        rx1, ry1 = ox + x1 * sx, oy + y1 * sy
        left, right = 2 * rx0 / win_w - 1, 2 * rx1 / win_w - 1
        top, bottom = 1 - 2 * ry0 / win_h, 1 - 2 * ry1 / win_h
        glLineWidth(2.0)
        glColor3f(1, 1, 0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(left, bottom)
        glVertex2f(right, bottom)
        glVertex2f(right, top)
        glVertex2f(left, top)
        glEnd()

    # ------------------- Mouse Handling -------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.start_pos = self.end_pos = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            self.end_pos = event.pos()
            self._finalize_bbox()
            self.update()

    def _compute_temp_bbox(self):
        if not self.start_pos or not self.end_pos:
            return None
        x0, y0 = self._widget_to_image(self.start_pos.x(), self.start_pos.y())
        x1, y1 = self._widget_to_image(self.end_pos.x(), self.end_pos.y())
        return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

    def _finalize_bbox(self):
        if not self.start_pos or not self.end_pos:
            self.last_bbox = None
            return
        x0, y0 = self._widget_to_image(self.start_pos.x(), self.start_pos.y())
        x1, y1 = self._widget_to_image(self.end_pos.x(), self.end_pos.y())
        if abs(x1 - x0) < 2 or abs(y1 - y0) < 2:
            self.last_bbox = None
            return
        self.last_bbox = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

    def _widget_to_image(self, px, py):
        ox, oy, w, h = self._compute_aspect_fit(self.tex_width, self.tex_height,
                                                self.width(), self.height())
        ix = px - ox
        iy = py - oy
        ix = max(0, min(ix, w))
        iy = max(0, min(iy, h))
        img_x = int(ix * self.tex_width / w)
        img_y = int(iy * self.tex_height / h)
        return img_x, img_y

    # ------------------- Public API -------------------
    def load_source(self, path: str) -> bool:
        """Load image or video, stop previous playback, reset state."""
        p = Path(path)
        if not p.exists():
            return False

        suffix = p.suffix.lower()

        # Stop existing video
        if self.video_timer:
            self.video_timer.stop()
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None

        # Reset state
        self.last_bbox = None
        self.mask = None
        self.mask_tex = None
        self._video_start_time = None
        self.video_fps = 0

        # Image
        if suffix in ('.jpg', '.jpeg', '.png'):
            img_bgr = cv2.imread(str(p))
            if img_bgr is None:
                return False
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            self.current_frame = img_rgb
            self.current_image_path = str(p.name)
            self._upload_frame_to_texture(img_rgb)
            self.update()
            return True

        # Video
        if suffix in ('.mov', '.mp4'):
            cap = cv2.VideoCapture(str(p))
            if not cap.isOpened():
                return False
            self.video_cap = cap
            self.current_image_path = str(p.name)

            ret, frame = cap.read()
            if not ret:
                return False
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = frame_rgb
            self._upload_frame_to_texture(frame_rgb)

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.video_fps = fps
            self._video_start_time = time.perf_counter()

            if self.video_timer is None:
                self.video_timer = QTimer(self)
                self.video_timer.timeout.connect(self._advance_video_frame)
            self.video_timer.start(15)  # short polling interval
            return True

        return False

    # ------------------- Video Playback -------------------
    def _advance_video_frame(self):
        """Advance video frame according to precise video timestamps (real-time)."""
        if self.video_cap is None or self.video_fps <= 0:
            return

        now = time.perf_counter()
        if self._video_start_time is None:
            self._video_start_time = now

        # get video timestamp of next frame
        ret, frame = self.video_cap.read()
        if not ret:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_cap.read()
            if not ret:
                return

        frame_ts = self.video_cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        elapsed = now - self._video_start_time
        sleep_time = frame_ts - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.current_frame = frame_rgb
        self._upload_frame_to_texture(frame_rgb)
        self.update()

    # ------------------- Masks and BBox -------------------
    def apply_mask(self, mask_np):
        self.mask = mask_np
        self.update()

    def toggle_mask_visibility(self):
        self.mask_visible = not self.mask_visible
        self.update()

    def get_last_bbox(self):
        return self.last_bbox

    # ------------------- Video Controls -------------------
    def play_video(self):
        if self.video_cap and self.video_timer:
            self.video_timer.start(15)

    def pause_video(self):
        if self.video_timer:
            self.video_timer.stop()

    def stop_video(self):
        if self.video_cap:
            self.video_timer.stop()
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.current_frame = frame_rgb
                self._upload_frame_to_texture(frame_rgb)
                self.update()
