import os

LOGGER_NAME = "ThyraApp"

APP_DIR = os.path.dirname(__file__)
ICO_DIR = os.path.join(APP_DIR, 'ico')
HOME = os.path.expanduser("~")
THYRA_DIR = os.path.join(HOME, "Thyra")
THYRA_VIDEO_DIR = os.path.join(THYRA_DIR, "video")
THYRA_IMAGE_DIR = os.path.join(THYRA_DIR, "img")
THYRA_LOG_PATH = os.path.join(THYRA_DIR, "events.log")
