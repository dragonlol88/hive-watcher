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


def get_shared_variable(p_type: t.Type[t.Union[int, str, float, bool]],
                        init_value: t.Optional[t.Any] = None,
                        lock: bool = True):
    args = []
    if p_type not in TYPE_CODE:
        raise KeyError("%s is not supported variable types" % str(p_type))

    type_code = TYPE_CODE[p_type]
    args.append(type_code)
    if init_value:
        args.append(init_value)
    return multiprocessing.Value(*tuple(args), lock=lock)


class Supervisor:
    sec2day = 1 / 3600 * 24
    shared_variables = {"watcher": ('event_count', int, 0)}

    def __init__(self,
                 watcher: HiveWatcher,
                 reload_delay: t.Optional[float] = 5,
                 reload_interval: t.Optional[int] = None,
                 max_event: t.Optional[int] = None):

        self.watcher = watcher
        self.target = watcher.watch
        self.reload_delay = reload_delay
        self.reload_interval = reload_interval
        self.max_event = max_event
        self.pid = os.getpid()
        self.should_exit = threading.Event()
        self.start_time = time.time()

    def signal_handler(self, sig, frame):
        """
        A signal handler that is registered with the parent process.
        """
        self.should_exit.set()

    def watch(self):
        self.setup_variables_shared_with_watch()
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
        logger.info("Started reloader [%d]", self.pid)

    def shutdown(self):
        self.process.join()
        logger.info("Stopping Supervisor [%d]", self.pid)

    def setup_variables_shared_with_watch(self):

        for obj_name, info  in self.shared_variables.items():
            var, typ, init = info
            setattr(self,
                    var,
                    get_shared_variable(typ, init))

            self._share_variable(obj_name, var, self.__dict__[var])

    def _share_variable(self, target, var, value):

        if not hasattr(self, target):
            raise AttributeError(
                "Supervisor does not have %s attribute" % target)
        else:
            target_obj = getattr(self, target)
            if not hasattr(target_obj, var):
                raise AttributeError(
                    "%s does not have %s attribute" % (target_obj.__name__, var))

        setattr(target_obj, var, value)

    def should_reload(self):
        check_time = time.time()
        event_num = self.event_num
        if self.max_event < event_num:
            return True
        if self.reload_interval > (check_time - self.start_time) * self.sec2day:
            return True
        return False

    @property
    def event_num(self):
        return self.event_count.value
