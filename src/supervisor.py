import os
import sys
import time
import signal
import threading
import logging
import multiprocessing
import typing as t

from src.watcher import HiveWatcher
from src.loggy import configure_logging

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)

TYPE_CODE = {
    int  : 'H',
    bool : 'H',
    float: 'd',
    str  : 'u'
}

if sys.version_info > (3, 7):
    context = multiprocessing.get_context("fork")
else:
    context = multiprocessing


logger = logging.getLogger('awatcher')


def get_subprocess(target, **kwargs):
    try:
        stdin_fileno = sys.stdin.fileno()
    except OSError:
        stdin_fileno = None

    kw = {
        'target': target,
        'stdin_fileno': stdin_fileno
    }
    return context.Process(target=subprocess_started, kwargs=kw)


def subprocess_started(target, stdin_fileno):
    configure_logging()
    if stdin_fileno:
        sys.stdin = os.fdopen(stdin_fileno)

    target()


class Supervisor:
    sec2day = 1 / 3600 * 24

    def __init__(self,
                 watcher: HiveWatcher,
                 reload_delay: t.Optional[float] = 5):

        self.watcher = watcher

        self.target = watcher.watch
        self.reload_delay = reload_delay
        self.pid = os.getpid()
        self.should_exit = threading.Event()
        self.start_time = time.time()

    def signal_handler(self, sig, frame):
        """
        A signal handler that is registered with the parent process.
        """
        self.should_exit.set()

    def watch(self):
        self.startup()
        while not self.should_exit.wait(self.reload_delay) and \
                self.process.is_alive():
            if self.should_reload():
                self.restart()
        self.shutdown()

    def startup(self):

        logger.info("Started Supervisor process [%d]",
                    self.pid)

        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self.signal_handler)

        self.process = get_subprocess(self.target)
        self.process.start()

    def restart(self):
        # logging
        self.process.terminate()
        self.process.join()
        self.process = get_subprocess(self.target)
        self.process.start()
        self.watcher.initialize_reload_watcher()

        logger.info("Started reloader [%d]", self.pid)

    def shutdown(self):
        self.process.join()
        logger.info("Stopping Supervisor [%d]", self.pid)

    def should_reload(self):
        return self.watcher.should_reload_watcher
