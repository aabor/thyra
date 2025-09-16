
import os
import multiprocessing as mp
from PySide6.QtWidgets import QApplication
from pathlib import Path
from app.workers.sam_worker import SamWorker
from app.workers.density_worker import DensityWorker


class ThyraApp(QApplication):
    """Custom QApplication for Thyra.
    Responsibilities:
      - ensure user folder exists at ~/Thyra
      - create worker processes (stubs)
      - provide queues for IPC
    """
    def __init__(self, argv):
        super().__init__(argv)
        # user folder
        self.user_folder = Path.home() / 'Thyra'
        self.user_folder.mkdir(parents=True, exist_ok=True)

        # multiprocessing queues
        self.req_q = mp.Queue()
        self.res_q = mp.Queue()

        # start worker stubs
        self.sam_worker = SamWorker(self.req_q, self.res_q)
        self.density_worker = DensityWorker(self.req_q, self.res_q)
        self.sam_worker.start()
        self.density_worker.start()

    def shutdown(self):
        try:
            # send termination signals
            self.req_q.put(None)
            self.req_q.put(None)
            self.sam_worker.join(timeout=2)
            self.density_worker.join(timeout=2)
        except Exception:
            pass
