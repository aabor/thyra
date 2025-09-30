# !/usr/bin/env python3
import sys
import multiprocessing as mp
import os
import logging
from logging.handlers import RotatingFileHandler

from app.ui.main_window import MainWindow
from app.app import ThyraApp
from configuration import LOGGER_NAME, THYRA_LOG_PATH

logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(THYRA_LOG_PATH, maxBytes=1_000_000, backupCount=5)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("Application started")


def main():
    # Ensure spawn start method for cross-platform compatibility
    mp.set_start_method('spawn', force=True)

    app = ThyraApp(sys.argv)

    window = MainWindow(app)
    window.showMaximized()
    window.activateWindow()

    exit_code = app.exec()

    # clean up workers
    app.shutdown()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
