import os
import sys
import time
import signal
import threading
import multiprocessing
import typing as t

from .hivewatcher import HiveWatcher

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)

TYPE_CODE = {
    int: 'H',
    float: 'd',
    str: 'u'
}


def get_subprocess(target, **kwargs):


    try:
        stdin_fileno = sys.stdin.fileno()
    except OSError:
        stdin_fileno = None

    kw = {
        'target': target,
        'stdin_fileno': stdin_fileno
    }

    return multiprocessing.Process(target=subprocess_started, kwargs=kw)


def subprocess_started(target, stdin_fileno):

    if stdin_fileno:
        sys.stdin = os.fdopen(stdin_fileno)

    target()


def get_shared_variable(p_type: t.Type[t.Union[int, str, float]],
                        init_value: t.Optional[t.Any] = None,
                        lock: t.Optional[bool] = True):

    args = []
    if p_type not in TYPE_CODE:
        raise KeyError("%s is not supported variable types" % str(p_type))

    type_code = TYPE_CODE[p_type]
    args.append(type_code)
    if init_value:
        args.append(init_value)

    args = tuple(args)

    return multiprocessing.Value(*args, lock=lock)


class Supervisor:

    sec2day = 1 / 3600 * 24

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
        self.startime = time.time()

    def signal_handler(self, sig, frame):
        """
        A signal handler that is registered with the parent process.
        """
        self.should_exit.set()

    def watch(self):
        self.setup_watch()
        self.startup()
        while not self.should_exit.wait(self.reload_delay):
            if self.should_reload:
                self.restart()

        self.shutdown()

    def startup(self):

        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self.signal_handler)

        self.process = get_subprocess(self.target)
        self.process.start()

    def restart(self):

        self.process.terminate()
        self.process.join()
        print('reload start')
        self.process = get_subprocess(self.target)
        self.process.start()

    def shutdown(self):
        self.process.join()

        # logger

    def setup_watch(self):

        self.event_num = get_shared_variable(type(self.max_event), 0)
        self.watcher.event_count = self.event_num

    @property
    def should_reload(self):
        check_time = time.time()
        event_num = self.event_num.value
        if self.max_event < event_num:
            return True

        if self.reload_interval > (check_time-self.startime)*self.sec2day:
            return True

        return False

