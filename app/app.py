import os
import multiprocessing as mp
import threading
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.workers.sam_worker import SamWorker
from app.workers.density_worker import DensityWorker


class ThyraApp(QApplication):
    """Custom QApplication for Thyra with async worker startup."""

    def __init__(self, argv):
        super().__init__(argv)

        # user folder
        self.user_folder = Path.home() / 'Thyra'
        self.user_folder.mkdir(parents=True, exist_ok=True)

        # multiprocessing queues
        self.req_q = mp.Queue()
        self.res_q = mp.Queue()

        # workers will be created in background thread
        self.sam_worker: SamWorker | None = None
        self.density_worker: DensityWorker | None = None

        # start workers asynchronously
        self._start_workers_async()

    # --------------------------------------
    # Asynchronous worker startup
    # --------------------------------------
    def _start_workers_async(self):
        """Start SamWorker and DensityWorker in a separate thread."""
        def worker_init():
            self.sam_worker = SamWorker(self.req_q, self.res_q)
            self.density_worker = DensityWorker(self.req_q, self.res_q)
            self.sam_worker.start()
            self.density_worker.start()
            print("[ThyraApp] Worker processes started in background thread.")

        thread = threading.Thread(target=worker_init, daemon=True)
        thread.start()

    # --------------------------------------
    # Shutdown
    # --------------------------------------
    def shutdown(self):
        try:
            # send termination signals
            if self.req_q:
                self.req_q.put(None)
                self.req_q.put(None)

            # join workers if they exist
            if self.sam_worker:
                self.sam_worker.join(timeout=2)
            if self.density_worker:
                self.density_worker.join(timeout=2)
        except Exception:
            pass