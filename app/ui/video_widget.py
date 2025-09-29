from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtOpenGLWidgets import QOpenGLWidget


class VideoWidget(QOpenGLWidget):
    """QOpenGLWidget for video or image output."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAutoFillBackground(False)
        self.image: QImage | None = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.image:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            pixmap = QPixmap.fromImage(self.image)
            painter.drawPixmap(self.rect(), pixmap)
