from __future__ import annotations
from typing import Tuple

from PySide6.QtCore import QRectF, QPointF


def compute_video_rect(img_w: int, img_h: int, widget_w, widget_h) -> QRectF:
    """Compute rectangle (in widget coordinates) where the image/video is drawn.

    Centers and scales the image to fit while preserving aspect ratio (letterbox).
    """

    if img_w <= 0 or img_h <= 0:
        return QRectF(0, 0, widget_w, widget_h)

    widget_ratio = widget_w / widget_h
    img_ratio = img_w / img_h

    if widget_ratio > img_ratio:
        # Widget is wider -> fit height, center horizontally
        height = widget_h
        width = img_ratio * height
        x_offset = (widget_w - width) / 2.0
        y_offset = 0.0
    else:
        # Widget is taller -> fit width, center vertically
        width = widget_w
        height = width / img_ratio
        x_offset = 0.0
        y_offset = (widget_h - height) / 2.0

    return QRectF(x_offset, y_offset, width, height)


def widget_to_image_coords(pos: QPointF,
                           img_w: int, img_h: int,
                           widget_w: int, widget_h: int,
                           rect: QRectF | None = None) -> Tuple[float,
float]:
    """Map widget coordinates -> absolute image coordinates (pixels).

    Accepts optional precomputed rect to avoid recomputing inside paint loops.
    """
    if rect is None:
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

    if img_w <= 0 or img_h <= 0:
        return 0.0, 0.0

    # relative coords inside image rect
    x_rel = (pos.x() - rect.x()) / rect.width()
    y_rel = (pos.y() - rect.y()) / rect.height()

    # clamp to [0,1]
    x_rel = min(max(0.0, x_rel), 1.0)
    y_rel = min(max(0.0, y_rel), 1.0)

    # convert to absolute image pixels
    x_img = x_rel * img_w
    y_img = y_rel * img_h
    return x_img, y_img


def image_to_widget_coords(x_img: float, y_img: float,
                           img_w: int, img_h: int,
                           widget_w: int, widget_h: int,
                           rect: QRectF | None = None) -> QPointF:
    """Map absolute image coordinates (pixels) -> widget coordinates (QPointF)."""
    if rect is None:
        rect = compute_video_rect(img_w, img_h, widget_w, widget_h)

    if img_w <= 0 or img_h <= 0:
        return QPointF(0.0, 0.0)

    x_rel = x_img / img_w
    y_rel = y_img / img_h

    x_widget = rect.x() + x_rel * rect.width()
    y_widget = rect.y() + y_rel * rect.height()
    return QPointF(x_widget, y_widget)
