# !/usr/bin/env python3
import sys
import multiprocessing as mp
import os

from app.ui.main_window import MainWindow
from app.app import ThyraApp


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
