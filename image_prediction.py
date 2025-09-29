import numpy as np
import cv2
import torch
from sam2.sam2_image_predictor import SAM2ImagePredictor

predictor = SAM2ImagePredictor.from_pretrained(
    "facebook/sam2-hiera-large",
    device="cpu"
)

# Load with OpenCV (BGR) → convert to RGB
image = cv2.imread("./img/IMG_7932.jpeg")
image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


points = np.array([[50, 75], [250, 200]])  # Coordinates in (x,y) format
labels = np.array([0, 1])                    # 1=foreground, 0=background

with torch.inference_mode(), torch.autocast("cpu", dtype=torch.bfloat16):
    predictor.set_image(image)  # numpy array HxWxC (RGB)
    masks, _, _ = predictor.predict(
    point_coords=points,      # Nx2 array of (x,y) point coordinates
    point_labels=labels,      # N array of labels (1=foreground, 0=background)
    # box=box,                  # 4-element array [x1, y1, x2, y2] of box coordinates
    # mask_input=prev_mask,     # Optional mask from previous prediction
    # multimask_output=True,    # Whether to return multiple mask options
    # return_logits=False       # Whether to return logits or binary masks
    )

    print(masks)