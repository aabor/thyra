
import multiprocessing as mp
import numpy as np
import time
import cv2

class SamWorker(mp.Process):
    """Stub worker: listens for segment requests and responds with a rectangular mask."""
    def __init__(self, req_q, res_q):
        super().__init__()
        self.req_q = req_q
        self.res_q = res_q

    def run(self):
        while True:
            req = self.req_q.get()
            if req is None:
                break
            if req.get('type') == 'segment':
                box = req.get('box')
                # create a simple mask sized to a default or to image if provided
                # try to detect image size from request (optional)
                h = req.get('h', 480)
                w = req.get('w', 640)
                mask = np.zeros((h, w), dtype=np.uint8)
                if box:
                    x0, y0, x1, y1 = box
                    x0 = max(0, min(w-1, int(x0)))
                    x1 = max(0, min(w-1, int(x1)))
                    y0 = max(0, min(h-1, int(y0)))
                    y1 = max(0, min(h-1, int(y1)))
                    mask[y0:y1, x0:x1] = 255
                else:
                    # fallback small rect
                    mask[10:100, 10:200] = 255
                # generate response
                self.res_q.put({'request_id': req.get('request_id'), 'mask': mask})
            else:
                # ignore other types in stub
                time.sleep(0.01)