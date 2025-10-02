from dataclasses_json import dataclass_json
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy.interpolate import splprep, splev
from shapely.geometry import LineString
from shapely.ops import unary_union

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF, QColor

from app.computational_geometry.coordinates_convertion import \
    image_to_widget_coords
from app.ui.vector_masks import VectorMask, register_vector_mask_object


@register_vector_mask_object
@dataclass_json
@dataclass
class PolygonShape(VectorMask):
    points: List[Tuple[float, float]]
    id: str
    ts: int  # timestamp

    def __post_init__(self):
        self.selected = False

    def get_points(self) -> List[Tuple[float, float]]:
        return self.points

    def draw(self, painter: QPainter,
             img_w: int, img_h: int, widget_w: int, widget_h: int,
             rect: QRectF, pen: QPen):
        pts = [image_to_widget_coords(
            x * img_w, y * img_h,
            img_w, img_h, widget_w, widget_h, rect)
            for x, y in self.points]
        if len(pts) >= 3:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF(pts))

    def update(self, x_img_norm: float, y_img_norm: float):
        """Append new vertex if it is far enough from the last one."""
        last_x, last_y = self.points[-1]
        if abs(last_x - x_img_norm) > 0.002 or abs(last_y - y_img_norm) > 0.002:
            self.points.append((x_img_norm, y_img_norm))

    def smooth(self, image_width: int, image_height: int,
               screen_width_mm: float = None, screen_height_mm: float = None,
               min_point_distance_mm: float = 3.0):
        """
        Smooth polygon after drawing:
        - Redistribute points along spline curve.
        - Remove self-intersections using low-level geometry operations.
        - Remove points closer than min_point_distance_mm (screen mm).
        - Convert points back to normalized coordinates.
        """
        if len(self.points) < 3:
            return

        # Convert normalized points to absolute pixels
        pts_px = np.array(
            [(x * image_width, y * image_height) for x, y in self.points])
        x, y = pts_px[:, 0], pts_px[:, 1]

        # Convert to screen mm
        scale_x = screen_width_mm / image_width
        scale_y = screen_height_mm / image_height
        x_mm, y_mm = x * scale_x, y * scale_y

        # Close polygon for spline
        x_closed = np.append(x_mm, x_mm[0])
        y_closed = np.append(y_mm, y_mm[0])

        # --- Periodic spline ---
        try:
            tck, _ = splprep([x_closed, y_closed], s=0, per=True)
        except Exception:
            self.points = [(xi / image_width, yi / image_height) for xi, yi in
                           zip(x, y)]
            return

        # Evaluate spline densely
        perimeter_mm = np.sum(
            np.sqrt(np.diff(x_closed) ** 2 + np.diff(y_closed) ** 2))
        num_points = max(int(perimeter_mm / min_point_distance_mm * 2),
                         len(self.points) * 2)
        u_new = np.linspace(0, 1, num_points)
        x_spline, y_spline = splev(u_new, tck)

        # --- Remove self-intersections ---
        line = LineString(np.column_stack([x_spline, y_spline]))
        simple_line = unary_union(line)  # removes self-intersections
        if simple_line.geom_type == "LineString":
            coords = list(simple_line.coords)
        elif simple_line.geom_type == "MultiLineString":
            # take the longest line as approximation
            coords = max((list(ls.coords) for ls in simple_line.geoms),
                         key=lambda c: len(c))
        else:
            coords = list(np.column_stack([x_spline, y_spline]))

        # Filter points too close
        new_pts_mm = [coords[0]]
        for pt in coords[1:]:
            prev_pt = new_pts_mm[-1]
            dist_mm = np.linalg.norm(np.array(pt) - np.array(prev_pt))
            if dist_mm >= min_point_distance_mm:
                new_pts_mm.append(pt)

        # Convert back to normalized coordinates
        self.points = [
            (x_mm / scale_x / image_width, y_mm / scale_y / image_height)
            for x_mm, y_mm in new_pts_mm]

    def move(self, dx: float, dy: float):
        """Move polygon in normalized coordinates, clamped inside [0,1]."""
        new_points = []
        for x, y in self.points:
            nx = min(max(x + dx, 0.0), 1.0)
            ny = min(max(y + dy, 0.0), 1.0)
            new_points.append((nx, ny))
        self.points = new_points

    def move_point(self, index: int, nx: float, ny: float) -> None:
        """Move single vertex at `index` to normalized coords (nx,ny)."""
        if index < 0 or index >= len(self.points):
            return
        nx = min(max(nx, 0.0), 1.0)
        ny = min(max(ny, 0.0), 1.0)
        pts = list(self.points)
        pts[index] = (nx, ny)
        self.points = pts

    def delete_point(self, index: int) -> bool:
        """Delete a specific vertex if polygon will still have >= 3 points."""
        if len(self.points) <= 3:
            return False
        if index < 0 or index >= len(self.points):
            return False
        pts = list(self.points)
        pts.pop(index)
        self.points = pts
        return True

    def contains(self, nx: float, ny: float) -> bool:
        """Ray casting point-in-polygon check in normalized coords."""
        inside = False
        pts = self.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > ny) != (yj > ny)) and \
                (nx < (xj - xi) * (ny - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def draw_points(self, painter, img_w, img_h, widget_w, widget_h, rect,
                    active_index: int | None = None,
                    color=QColor(180, 180, 180)):
        pen = QPen(color, 2)
        painter.setPen(pen)
        for idx, (nx, ny) in enumerate(self.points):
            px = rect.left() + nx * rect.width()
            py = rect.top() + ny * rect.height()
            if active_index is not None and idx == active_index:
                painter.drawEllipse(int(px) - 5, int(py) - 5, 10, 10)
            else:
                painter.drawEllipse(int(px) - 3, int(py) - 3, 6, 6)

    def export_to_coco(self, image_id: int, ann_id: int, image_w: int,
                       image_h: int) -> dict:
        abs_points = []
        for x, y in self.points:
            abs_points.extend([x * image_w, y * image_h])
        return {
            "id": ann_id,
            "image_id": image_id,
            "category_id": 1,  # or map from self.id
            "segmentation": [abs_points],
            "area": 0,  # polygon area can be computed if needed
            "bbox": self._compute_bbox(image_w, image_h),
            "iscrowd": 0,
        }

    def _compute_bbox(self, image_w, image_h):
        xs = [x * image_w for x, _ in self.points]
        ys = [y * image_h for _, y in self.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return [min_x, min_y, max_x - min_x, max_y - min_y]
