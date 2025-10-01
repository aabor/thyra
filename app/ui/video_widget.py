from PySide6 import QtCore, QtGui
from PySide6.QtOpenGLWidgets import QOpenGLWidget


class VideoWidget(QOpenGLWidget):
    """QOpenGLWidget for video or image output."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAutoFillBackground(False)
        self.image: QtGui.QImage | None = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.image:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            pixmap = QtGui.QPixmap.fromImage(self.image)

            widget_w = self.width()
            widget_h = self.height()
            img_w = pixmap.width()
            img_h = pixmap.height()

            widget_ratio = widget_w / widget_h
            img_ratio = img_w / img_h

            if widget_ratio > img_ratio:
                # Widget is wider → fit height, center horizontally
                height = widget_h
                width = int(img_ratio * height)
                x_offset = int((widget_w - width) / 2)
                y_offset = 0
            else:
                # Widget is taller → fit width, center vertically
                width = widget_w
                height = int(width / img_ratio)
                x_offset = 0
                y_offset = int((widget_h - height) / 2)

            target_rect = QtCore.QRect(x_offset, y_offset, width, height)
            painter.drawPixmap(target_rect, pixmap)