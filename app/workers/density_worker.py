
import multiprocessing as mp
import time
import numpy as np

class DensityWorker(mp.Process):
    def __init__(self, req_q, res_q):
        super().__init__()
        self.req_q = req_q
        self.res_q = res_q

    def run(self):
        while True:
            req = self.req_q.get()
            if req is None:
                break
            if req.get('type') == 'density':
                # return a stub count
                count = 42
                # return also a small fake density map
                h = req.get('h', 480)
                w = req.get('w', 640)
                density = np.zeros((h, w), dtype=np.float32)
                density[h//2-10:h//2+10, w//2-10:w//2+10] = 1.0
                self.res_q.put({'request_id': req.get('request_id'), 'count': count, 'density': density})
            else:
                time.sleep(0.01)