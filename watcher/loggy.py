import sys
import logging
import logging.config

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG
}

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "watcher.loggy.DefaultFormatter",
            "fmt": "%(levelname)s - %(message)s (%(filename)s:%(lineno)d)",
            "datefmt": '%m/%d/%Y %I:%M:%S %p',
            "use_colors": True,
        },
        "file": {
            "()": "watcher.loggy.FileFormatter",
            "fmt": "%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)",
            "datefmt": '%m/%d/%Y %I:%M:%S %p',
            "use_colors": False,
        },

    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "logfile":
            {
                "formatter": "file",
                "class": "logging.FileHandler",
                "filename": "watcher.log"
            }
    },
    "loggers": {
        "watcher": {"handlers": ["default"], "level": "INFO"}
    }
}

COLORS = {
        'grey': "\x1b[38;21m",
        'green': "\x1b[32m",
        'yellow': "\x1b[33;21m",
        'red': "\x1b[31;21m",
        'bold_red': "\x1b[31;1m",

    }
RESET = "\x1b[0m"


class ColoredFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    FORMATS_COLOR = {
        logging.DEBUG: COLORS['grey'],
        logging.INFO: COLORS['grey'],
        logging.WARNING: COLORS['yellow'],
        logging.ERROR: COLORS['red'],
        logging.CRITICAL: COLORS['bold_red']
    }

    def __init__(self, fmt=None, datefmt=None, style="%", use_colors=None):

        if use_colors:
            self.use_colors = use_colors
        else:
            self.use_colors = sys.stdout.isatty()

        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def set_colored_fmt(self, record):
        color = self.FORMATS_COLOR[record.levelno]
        self._style._fmt = color + self._fmt + RESET

    def _custom_record(self, record):
        raise NotImplementedError

    def custom_record(self, record):

        if self.use_colors and not hasattr(record, 'color'):
            self.set_colored_fmt(record)
        record = self._custom_record(record)
        return record

    def formatMessage(self, record) -> str:
        record = self.custom_record(record)
        return super().formatMessage(record)


class DefaultFormatter(ColoredFormatter):

    def _custom_record(self, record):
        color = record.__dict__.get('color', None)
        if color:
            self._style._fmt = COLORS[color] + self._fmt + RESET
        return record


class FileFormatter(ColoredFormatter):

    def _custom_record(self, record):
        return record


class EventFormatter(ColoredFormatter):

    def _custom_record(self, record):
        pass


def configure_logging():
    logging.config.dictConfig(LOGGING_CONFIG)