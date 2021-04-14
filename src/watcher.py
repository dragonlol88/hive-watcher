import os
import time
import queue
import asyncio
import signal
import threading
import typing as t
import logging
import multiprocessing

from . import common as c

from .loops.asyncio_loop import asyncio_setup
from .buffer import EventNotify


if t.TYPE_CHECKING:
    from .common import Task, Loop

DEFAULT_QUEUE_TIMEOUT = 0.01
# From uvicorn
HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)

logger = logging.getLogger('awatcher')


def _set_loop(kind):
    """
    Method to set loop kind
    :param kind:
        'asyncio', 'uvloop'( scheduled in the future)
    """
    if kind == 'asyncio':
        asyncio_setup()


async def execute_event(task, event):
    """
    Execute event and log task

    :param task:
        Loop task
    :param event:
        Event Coroutine
    """
    try:
        await task
    except Exception as e:
        # log 찍기
        print(e, event)


class WatcherState:
    processes = []
    time_from_reload = time.time()
    total_event = 0
    reload_watcher = multiprocessing.Event()

class HiveWatcher:

    def __init__(self,
                 config
                 ):

        self._lock = threading.Lock()
        self._event_queue = c.EventQueue()
        self.state = WatcherState()
        self.should_exit = False
        self.config = config
        self.max_event = config.max_event
        self.reload_watcher = self.state.reload_watcher
        self.processes = self.state.processes
        self.reload_interval = self.config.reload_interval
        self.shutdown_timeout = config.shutdown_timeout
        self.start = None

        # self._processes = self.state.processes
        # self._time_from_reload = watcher.state.time_from_reload
        # self._total_event = watcher.state.total_event
        # self._should_reload_watcher = watcher.state.should_reload_watcher
        #
    def watch(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.run())

    async def run(self):
        process_id = os.getpid()
        loop = asyncio.get_event_loop()
        # await self.file_io.read()

        config = self.config
        if config:
            config.load()

        self.install_signal_handlers()
        message = 'Started awatcher process [%d]'
        logger.info(message,
                    process_id)
        await self.startup()

        if self.should_exit:
            return
        await self.main_loop()
        await self.shutdown()

        message = "Finished server process [%d]"
        logger.info(
            message,
            process_id
        )

    async def startup(self):
        self.start = time.time()
        loop = asyncio.get_event_loop()
        event_queue = self._event_queue
        config = self.config
        host = config.noti_host
        port = config.noti_port

        await self.read_file()
        self.notify = EventNotify(config, event_queue)
        try:
            self.pool = config.create_pool(self, event_queue)
            await self.pool.start()
        except Exception as e:
            message = "Fail initialize Hive Watcher Pool [%s]"
            logger.error(
                message,
                str(e)
            )
            self.should_exit = True

        self._log_started_message()

    def _log_started_message(self):
        if not hasattr(self, 'scheme'):
            self.scheme = 'http'
        port = self.config.noti_port
        host = self.config.noti_host
        root_dir = self.config.lookup_dir
        remote_notify_message = "Remote Notifier running on %s://%s:%d (Press Ctrl + C to quit)"
        logger.info(remote_notify_message,
                    self.scheme,
                    host,
                    port)
        local_notify_fmt = "Local Notifier is watching at %s (Press Ctrl + C to quit)"
        logger.info(local_notify_fmt, root_dir)

    async def main_loop(self):
        should_exit = await self.buzz()
        while not should_exit:
            await asyncio.sleep(2)
            should_exit = await self.buzz()

    async def buzz(self):

        if self.max_event:
            if self.state.total_event > self.max_event:
                self.reload_commands()

        if self.reload_interval*3600 > time.time() - self.start:
            self.reload_commands()

        # 나중에 callback notify 추가 하기

        if self.should_exit:
            return True
        return False

    def reload_commands(self):
        self.notify_reload_signal()
        self.state.total_event = 0
        self.start = time.time()

    async def shutdown(self):
        """
        Shutting down awatcher.
        """
        start = time.time()
        # Todo 로그찍기
        # First, stop the watcher pool processing.
        await self.pool.stop()

        # Gather events from event_queue and put event in tasks set.
        while self.processes:
            if self.shutdown_timeout > time.time() - start:
                break
            process = self.processes.pop()
            if process._state == c._PENDING:
                self.processes.append(process)

        await self.write_file()

    async def read_file(self):
        pass

    async def write_file(self):
        pass

    @property
    def should_reload_watcher(self):
        return self.reload_watcher.is_set()

    def notify_reload_signal(self):
        self.reload_watcher.set()

    def initialize_reload_watcher(self):
        self.reload_watcher.clear()

    def get_event_queue(self):
        return self._event_queue.get(timeout=0)

    @property
    def event_queue(self):
        return self._event_queue

    def install_signal_handlers(self, loop: t.Optional[c.Loop] = None) -> None:

        if threading.current_thread() is not threading.main_thread():
            # Signals can only be listened to from the main thread.
            return

        if loop is None:
            loop = asyncio.get_event_loop()

        try:
            for sig in HANDLED_SIGNALS:
                loop.add_signal_handler(sig, self.handle_exit, sig, None)
        except NotImplementedError:
            # Windows
            for sig in HANDLED_SIGNALS:
                signal.signal(sig, self.handle_exit)

    def handle_exit(self, sig, frame):
        self.should_exit = True
