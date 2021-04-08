import os
import time
import queue
import asyncio
import signal
import threading
import typing as t
import logging

from .io_ import FileIO
from .type import Loop
from .common import EventQueue
from .manager_pool import ManagerPool
from .manager import HTTPManager
from .transport import Transporter
from .emitter import EventEmitter
from .loops.asyncio_loop import asyncio_setup


if t.TYPE_CHECKING:
    from src.events import EventBase as Event
    from src.type import Task, Loop

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


class HiveWatcher:

    def __init__(self,
                 host: str,
                 port: int,
                 manager_path: str,
                 connection_class,
                 files_path: str,
                 loop_kind: str,
                 root_dir: str,
                 ignore_pattern: str,
                 proj_depth: int = 1,
                 timeout: t.Optional[float] = DEFAULT_QUEUE_TIMEOUT,
                 record_interval_minute: t.Optional[float] = 5,
                 max_event: t.Optional[int] = None,
                 retry_on_timeout = False
                 ):

        self._lock = threading.Lock()
        self._event_queue = EventQueue()

        # queue get timeout
        self._timeout = timeout

        # notify parameter
        self.host = host
        self.port = port

        self.root_dir = root_dir
        self.ignore_pattern = ignore_pattern
        self.proj_depth = proj_depth

        self.files: t.Dict[str, t.Tuple[str, float]] = {}
        self.files_path = files_path

        # loop kind
        self.loop_kind = loop_kind

        # watches record_interval
        self.record_interval_minute = record_interval_minute

        # exit flag
        self.should_exit = False
        self.supervisor_exit = False
        # exit event
        self.exit_notify = threading.Event()

        # max event number
        # If event occur over the max event, restart watch continually
        self.max_event = max_event

        # storage place of watch information
        self.manager_path = manager_path

        # watch writer
        # Write the watches in files to protect the remote servers information
        # when awatcher down

        self.file_io = FileIO(self.files_path, self.files)
        # event count
        self.event_count = None

        # tasks
        self.tasks: t.Set[t.Tuple[Task, Event]] = set()

        # awatcher start time
        self.start_time = time.time()

        self.manager_pool_class = ManagerPool
        self.manager_class = HTTPManager
        self.transporter = Transporter(connection_class, retry_on_timeout)
        self.retry_on_timeout = retry_on_timeout

    def watch(self):
        _set_loop(self.loop_kind)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.run())

    async def run(self):
        process_id = os.getpid()

        loop = asyncio.get_event_loop()
        self.manager_pool = self.manager_pool_class(loop, self.manager_class, self.manager_path)
        await self.manager_pool.read()
        # await self.file_io.read()

        self.install_signal_handlers()
        loop = asyncio.get_event_loop()

        message = 'Started awatcher process [%d]'
        logger.info(message,
                    process_id)

        self.start_up_emitter()
        if self.should_exit:
            return

        self.emit = loop.create_task(self.emit())

        await self.main_loop()
        await self.shutdown()

        message = "Finished server process [%d]"
        logger.info(
            message,
            process_id
        )

    def start_up_emitter(self):
        loop = asyncio.get_event_loop()
        event_queue = self._event_queue
        timeout = self.timeout
        params = {
            "localnotify_root_dir": self.root_dir,
            "localnotify_ignore_pattern": self.ignore_pattern,
            "localnotify_proj_depth": self.proj_depth,
            "localnotify_files": self.files,
            "remotenotify_host": self.host,
            "remotenotify_port": self.port
        }
        try:
            self.emitter = EventEmitter(self, event_queue, loop, **params)
            self.emitter.start()
            # log emitter started message
        except Exception as e:
            message = "Fail initialize Hive Watcher Emitter [%s]"
            logger.error(
                message,
                str(e)
            )
            self.should_exit = True

    async def emit(self):

        count = 0
        self._log_started_message()
        while not self.should_exit:
            try:
                task, event = self.get_event_queue()

                # Put event in task set
                self.tasks.add((task, event))
                if self.event_count is not None:
                    count += 1
                    setattr(self.event_count, 'value', count)
            except queue.Empty:
                await asyncio.sleep(0.4)

    def _log_started_message(self):
        if not hasattr(self, 'scheme'):
            self.scheme = 'http'

        remote_notify_message = "Remote Notifier running on %s://%s:%d (Press Ctrl + C to quit)"
        logger.info(remote_notify_message,
                    self.scheme,
                    self.host,
                    self.port)

        local_notify_fmt = "Local Notifier is watching at %s (Press Ctrl + C to quit)"
        logger.info(local_notify_fmt,
                    self.root_dir)

    async def main_loop(self):
        """

        :return:
        """
        should_exit = await self.buzz()
        while not should_exit:
            now = time.time()
            await asyncio.sleep(0.1)
            should_exit = await self.buzz(now)

    async def buzz(self, now=None):
        """

        :param now:
            Current time
        :return:
        """
        # Express start signal
        if now is None:
            return False

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
