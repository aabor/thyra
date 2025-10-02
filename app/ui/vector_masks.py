import uuid
from datetime import datetime
from typing import Dict, Type, List
from abc import ABC, abstractmethod

from dataclasses import dataclass

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPen, QColor
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class VectorMask(ABC):

    @classmethod
    def create(cls, mask_type: str, x: float = 0.0,
               y: float = 0.0) -> 'VectorMask':
        """
        Factory method to create a new VectorMask subclass instance.
        Args:
            mask_type: 'box' or 'poly'
            x, y: starting normalized coordinates
        Returns:
            Instance of BoundingBox or PolygonShape
        """
        ts = int(datetime.now().timestamp())
        new_id = str(uuid.uuid4())
        if mask_type == "box":
            from app.ui.bounding_box import BoundingBox
            return BoundingBox(x=x, y=y, w=0.0, h=0.0, id=new_id, ts=ts)
        elif mask_type == "poly":
            from app.ui.polygone_shape import PolygonShape
            return PolygonShape(points=[(x, y)], id=new_id, ts=ts)
        else:
            raise ValueError(f"Unknown mask_type: {mask_type}")

    @abstractmethod
    def draw(self, painter: QPainter,
             img_w: int, img_h: int, widget_w: int, widget_h: int,
             rect: QRectF, pen: QPen):
        pass

    def update(self, x_img_norm: float, y_img_norm: float):
        """Update the mask using the current mouse position (normalized coordinates)."""
        raise NotImplementedError

    @abstractmethod
    def smooth(self, image_width: int, image_height: int,
               screen_width_mm: float = None, screen_height_mm: float = None,
               min_point_distance_mm: float = 3.0):
        """Smooth the vector mask after completion. Stub in base class."""
        pass

    @abstractmethod
    def move(self, dx: float, dy: float):
        raise NotImplementedError

    @abstractmethod
    def contains(self, nx: float, ny: float) -> bool:
        raise NotImplementedError

    @abstractmethod
    def draw_points(self, painter, img_w, img_h, widget_w, widget_h, rect,
                    color=QColor(180, 180, 180)):
        raise NotImplementedError

    @abstractmethod
    def export_to_coco(self, image_id: int, ann_id: int, image_w: int,
                       image_h: int) -> dict:
        """Return COCO-style annotation dict."""
        raise NotImplementedError


_REGISTRY: Dict[str, Type[VectorMask]] = {}


def register_vector_mask_object(cls: Type[VectorMask]) -> Type[VectorMask]:
    """Class decorator to register VectorMask subclasses by name."""
    _REGISTRY[cls.__name__] = cls
    return cls


def get_vector_mask_class(name: str):
    return _REGISTRY.get(name)


def all_registered_names():
    return list(_REGISTRY.keys())


def vector_masks_encoder(objs: List[VectorMask]):
    return [
        {
            **(obj.to_dict() if hasattr(obj, "to_dict") else obj.__dict__),
            "type": obj.__class__.__name__,
        }
        for obj in objs
    ]


def vector_masks_decoder(data: List[dict]) -> List[VectorMask]:
    objs = []
    for item in data:
        if "type" in item:
            obj_cls = get_vector_mask_class(item["type"])
            if obj_cls is None:
                raise ValueError(f"Unknown VectorMask type: {item['type']}")
            obj_data = dict(item)
            obj_data.pop("type")
            if hasattr(obj_cls, "from_dict"):
                objs.append(obj_cls.from_dict(obj_data))
            else:
                objs.append(obj_cls(**obj_data))
    return objs
