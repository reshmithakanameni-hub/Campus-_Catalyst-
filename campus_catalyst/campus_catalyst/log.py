"""Central logging setup (audit trail). Writes to logs/campus_catalyst.log with rotation."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def get_logger(name):
    """Return a child of the 'campus_catalyst' logger, configuring file logging once."""
    root = logging.getLogger("campus_catalyst")
    if not root.handlers:
        root.setLevel(logging.INFO)
        root.propagate = False
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(LOG_DIR / "campus_catalyst.log", maxBytes=500_000,
                                          backupCount=3, encoding="utf-8")
        except OSError:                      # read-only disk: never crash the app over logging
            handler = logging.NullHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
    return root.getChild(name)
