import json
import os
from typing import List
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

from app.ui.vector_masks import vector_masks_encoder, vector_masks_decoder, \
    VectorMask


@dataclass_json
@dataclass
class ThyraDocument:
    src_file_path: str = ""
    src_file_type: str = ""  # 'video' or 'image'

    vector_masks: List[VectorMask] = field(
        default_factory=list,
        metadata=config(encoder=vector_masks_encoder,
                        decoder=vector_masks_decoder),
    )

    def __post_init__(self):
        self.action_stack: List[VectorMask] = []

    def undo(self):
        latest = []
        self.vector_masks.sort(key=lambda x: x.ts)
        if self.vector_masks:
            item = self.vector_masks.pop()
            self.action_stack.append(item)

    def redo(self) -> bool:
        if not self.action_stack:
            return False
        item = self.action_stack.pop()
        self.vector_masks.append(item)

    def clear(self):
        self.vector_masks.clear()

    def export_to_coco(self, image_width: int, image_height: int,
                       document_file_path: str):
        # Build COCO structure
        coco = {
            "images": [{
                "id": 1,
                "file_name": os.path.basename(self.src_file_path),
                "width": image_width,
                "height": image_height,
            }],
            "annotations": [],
            "categories": [{
                "id": 1,
                "name": "object",
                "supercategory": "none"
            }]
        }

        ann_id = 1
        for mask in sorted(self.vector_masks, key=lambda x: x.ts):
            ann = mask.export_to_coco(image_id=1, ann_id=ann_id,
                                      image_w=image_width, image_h=image_height)
            coco["annotations"].append(ann)
            ann_id += 1

        # Save to file with _coco.json suffix
        base, ext = os.path.splitext(document_file_path)
        out_path = f"{base}_coco.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(coco, f, indent=2)

        return out_path
