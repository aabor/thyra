from typing import Dict, Type, List
from abc import ABC, abstractmethod

from dataclasses import dataclass

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPen
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class VectorMask(ABC):
    @abstractmethod
    def draw(self, painter: QPainter,
             img_w: int, img_h: int, widget_w: int, widget_h: int,
             rect: QRectF, pen: QPen):
        pass

    @abstractmethod
    def export_to_coco(self, image_id: int, ann_id: int, image_w: int,
                       image_h: int) -> dict:
        """Return COCO-style annotation dict."""
        pass


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
