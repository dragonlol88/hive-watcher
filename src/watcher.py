import os
import time
import queue
import asyncio
import signal
import threading
import typing as t
import logging
import multiprocessing

from .common import EventQueue
from .watch_pool import WatchPool
from .loops.asyncio_loop import asyncio_setup
from .buffer import EventNotify


if t.TYPE_CHECKING:
    from src.events import EventBase as Event
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
    tasks = set()
    time_from_reload = time.time()
    total_event = 0
    should_reload_watcher = multiprocessing.Event()


class HiveWatcher:

    def __init__(self,
                 config
                 ):

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self.config = config

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
        loop = asyncio.get_event_loop()

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

        loop = asyncio.get_event_loop()
        event_queue = self._event_queue
        timeout = self.timeout
        config = self.config
        host = config.noti_host
        port = config.noti_port

        # 다시.................................
        self.notify = EventNotify(config, event_queue)

        try:
            self.pool = config.create_pool(event_queue, self, loop)
            await self.pool.start()
        except Exception as e:
            message = "Fail initialize Hive Watcher Emitter [%s]"
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
        root_dir = self.config.root_dir
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
            await asyncio.sleep(0.1)
            should_exit = await self.buzz()

    async def buzz(self):

        # pop task
        # If task is done, delete task
        # If task is not complicated, put task in task set
        while self.tasks:
            task, event = self.tasks.pop()
            if task.done():
                # task terminate
                del task
            else:
                self.tasks.add((task, event))

        # Write watch information in files
        if now - self.start_time >= self.record_interval_minute * 60:
            # await self.manager_pool.write()
            # await self.file_io.write()
            self.start_time = now

        if self.should_exit:
            return True

        return False

    async def shutdown(self):
        """
        Shutting down awatcher.
        """
        # Todo 로그찍기
        # First, stop the emitter processing.
        self.emitter.stop()

        # Gather events from event_queue and put event in tasks set.
        while True:
            try:
                task, event = self.get_event_queue()
            except queue.Empty:
                break
            self.tasks.add((task, event))

        # Complete additional events.
        while self.tasks:
            task, event = self.tasks.pop()
            await execute_event(task, event)

        # Record watches and file information.
        # await self.manager_pool.write()
        # await self.file_io.write()

    def get_event_queue(self):
        return self._event_queue.get(timeout=0)

    @property
    def event_queue(self):
        """
        Event queue
        """
        return self._event_queue

    @property
    def timeout(self):
        """
        Dequeue timeout
        :return:
        """
        return self._timeout

    def install_signal_handlers(self, loop: t.Optional[Loop] = None) -> None:
        """

        :param loop:
        :return:
        """
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
        """

        :param sig:
        :param frame:
        :return:
        """
        self.should_exit = True
