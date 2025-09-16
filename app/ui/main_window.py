from PySide6.QtWidgets import (QMainWindow, QToolBar, QFileDialog,
                               QStatusBar, QMessageBox)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QTimer
from pathlib import Path
import json
import time

from .gl_canvas import GLCanvas


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle('Thyra')

        # UI: toolbar
        toolbar = QToolBar('MainToolbar')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.action_create = QAction('Create', self)
        self.action_open_doc = QAction('Open Doc', self)
        self.action_open = QAction('Open Image/Video', self)
        self.action_segment = QAction('Segment (stub)', self)
        self.action_toggle_mask = QAction('Hide/Show Mask', self)
        self.action_save = QAction('Save (COCO/JSON)', self)

        toolbar.addAction(self.action_create)
        toolbar.addAction(self.action_open_doc)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_segment)
        toolbar.addAction(self.action_toggle_mask)
        toolbar.addAction(self.action_save)

        self.action_play = QAction('Play', self)
        self.action_pause = QAction('Pause', self)
        self.action_stop = QAction('Stop', self)

        toolbar.addAction(self.action_play)
        toolbar.addAction(self.action_pause)
        toolbar.addAction(self.action_stop)

        self.action_play.triggered.connect(lambda: self.canvas.play_video())
        self.action_pause.triggered.connect(lambda: self.canvas.pause_video())
        self.action_stop.triggered.connect(lambda: self.canvas.stop_video())

        # status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # central GL canvas
        self.canvas = GLCanvas(self)
        self.setCentralWidget(self.canvas)

        # connect actions
        self.action_open.triggered.connect(self.on_open)
        self.action_segment.triggered.connect(self.on_segment)
        self.action_save.triggered.connect(self.on_save)
        self.action_toggle_mask.triggered.connect(self.on_toggle_mask)
        self.action_create.triggered.connect(self.on_create)
        self.action_open_doc.triggered.connect(self.on_open_doc)

        # poll worker responses
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.poll_workers)
        self.poll_timer.start()

    def on_create(self):
        self.canvas.reset()
        self.status.showMessage('Created new document')

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open image or video',
                                              str(Path.cwd()),
                                              'Images/Videos (*.jpg *.jpeg *.mov *.mp4)')
        if path:
            ok = self.canvas.load_source(path)
            if ok:
                self.status.showMessage(f'Loaded: {path}')
            else:
                QMessageBox.warning(self, 'Open failed', 'Could not open file')

    def on_open_doc(self):
        path, _ = QFileDialog.getOpenFileName(self,
                                              'Open Thyra JSON doc (COCO subset)',
                                              str(self.app.user_folder),
                                              'JSON (*.json)')
        if not path:
            return
        with open(path, 'r') as f:
            data = json.load(f)
        # very small loader: if image entry present, try to load first image
        images = data.get('images', [])
        annotations = data.get('annotations', [])
        if images:
            img_entry = images[0]
            file_name = img_entry.get('file_name')
            candidate = Path(self.app.user_folder) / file_name
            if candidate.exists():
                self.canvas.load_source(str(candidate))
                self.canvas.load_annotations(annotations)
                self.status.showMessage(f'Document loaded: {path}')
            else:
                QMessageBox.warning(self, 'Open doc',
                                    f'Image {file_name} not found in {self.app.user_folder}')

    def on_segment(self):
        bbox = self.canvas.get_last_bbox()
        if bbox is None:
            self.status.showMessage('Draw a bounding box first')
            return
        # send stub request to worker
        req = {'type': 'segment', 'request_id': f'r{int(time.time())}',
               'box': bbox}
        self.app.req_q.put(req)
        self.status.showMessage('Segment request sent (stub)')

    def on_toggle_mask(self):
        self.canvas.toggle_mask_visibility()
        self.status.showMessage('Toggled mask visibility')

    def on_save(self):
        # collect data from canvas and save minimal COCO-like JSON
        doc = self.canvas.export_coco()
        ts = int(time.time())
        filename = f'session_{ts}.json'
        out_path = Path(self.app.user_folder) / filename
        with open(out_path, 'w') as f:
            json.dump(doc, f, indent=2)
        self.status.showMessage(f'Saved document to {out_path}')

    def poll_workers(self):
        # poll for responses from worker processes
        try:
            while not self.app.res_q.empty():
                msg = self.app.res_q.get_nowait()
                # handle segment stub
                if msg.get('mask') is not None:
                    self.canvas.apply_mask(msg['mask'])
                    self.status.showMessage('Mask received (stub)')
                if msg.get('count') is not None:
                    self.status.showMessage(
                        f"Density count (stub): {msg['count']}")
        except Exception:
            pass
