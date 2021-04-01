import time
import queue
import asyncio
import signal
import threading
import typing as t

from .common import BaseThread
from .common import EventQueue
from .common import WatchIO
from .loops.asyncio_loop import asyncio_setup

from .notify import Notify
from .events import HIVE_EVENTS
from .buffer import EventSymbol
from .type import Loop, Task
from .wrapper.response import WatcherConnector

if t.TYPE_CHECKING:
    from .events import EventBase as Event
    from .type import Task

DEFAULT_QUEUE_TIMEOUT = 1

# From uvicorn
HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


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


class Watch:

    """
    This class have purposes which monitor project file system
    and remote channels that use hive system. Current planned
    files are synonym and stopword files. If files are modified
    and created, automatically event is and raised files are
    transported to connected channels. The unit of watch is
    project.

    :param project
        Project name
    :param paths
        Managed file paths
    :param channels
        Managed remote server hosts
    :param target
        Raised file event paths
    :param lock
        Locking object
    """

    def __init__(self, project: str, loop: Loop):

        self._project = project
        self._paths: t.Set[str] = set()
        self._channels: t.Set[str] = {"http://127.0.0.1:6666/"}#set() # set() #{"http://127.0.0.1:6666/", "http://192.168.0.230:5112/
        self._loop = loop
        self._lock = asyncio.Lock(loop=loop)

    @property
    def paths(self) -> t.Set[str]:
        """
        The path that this watch monitors.
        """
        return self._paths

    @paths.setter
    def paths(self, paths: t.Set[str]):
        self._paths = paths

    @property
    def channels(self) -> t.Set[str]:
        """
        The channels that this watch monitors.
        """
        return self._channels

    @channels.setter
    def channels(self, channels: t.Set[str]):
        self._channels = channels

    @property
    def lock(self):
        """
        Threading lock object.
        """
        return self._lock

    @property
    def key(self) -> str:
        """

        :return:
        """
        return self._project

    def discard_path(self, path: str) -> None:
        """

        :param path:
        :return:
        """
        self._paths.discard(path)

    def add_path(self, path: str) -> None:
        """

        :param path:
        :return:
        """
        self._paths.add(path)

    def discard_channel(self, channel: str) -> None:
        """

        :param channel:
        :return:
        """
        self._channels.discard(channel)

    def add_channel(self, channel: str) -> None:
        """

        :param channel:
        :return:
        """
        self._channels.add(channel)

    def __eq__(self, watch: "Watch") -> bool: # type: ignore
        """

        :param watch:
        :return:
        """
        return self.key == watch.key

    def __ne__(self, watch: "Watch") -> bool:                                                 # type: ignore
        """

        :param watch:
        :return:
        """
        return self.key != watch.key

    def __hash__(self) -> int:
        """

        :return:
        """
        return hash(self.key)

    def __repr__(self) -> str:
        """

        :return:
        """
        return "<%s: project=%s>" % (
            type(self).__name__, self.key)


class EventEmitter(BaseThread):
    """
    :param loop
    :param event_queue
    :param timeout

    """
    def __init__(self,
                 loop: Loop,
                 event_queue: EventQueue,
                 timeout: float = DEFAULT_QUEUE_TIMEOUT):
        BaseThread.__init__(self)
        self.loop = loop
        self._event_queue = event_queue
        self._timeout = timeout

    @property
    def timeout(self):
        """
        Blocking timeout for reading events.
        """
        return self._timeout

    def queue_event(self, item: t.Tuple['Task', 'Event']):
        """
        Queues a single event.

        :param item:
            Event to be queued.
            event: <class:watcher.events.*>
        """
        self._event_queue.put(item)

    def queue_events(self, timeout: float):
        """Override this method to populate the event queue with events
        per interval period.

        :param timeout:
            Timeout (in seconds) between successive attempts at
            reading events.
        """

    def run(self):
        """
        :return:
        """
        while self.should_keep_running():
            self.queue_events(self.timeout)


class HiveEventEmitter(EventEmitter):

    connector_cls = WatcherConnector

    def __init__(self,
                 loop: Loop,
                 event_queue: EventQueue,
                 watches: t.Dict[str, Watch],
                 task_factory: t.Callable[[t.Coroutine], Task],
                 timeout: float = DEFAULT_QUEUE_TIMEOUT,
                 **params):
        super().__init__(loop, event_queue, timeout)

        self._lock = threading.Lock()
        self._watches = watches
        self._lock_factory = loop
        self._task_factory = task_factory
        self.params = params
        self.notify = None

    @property
    def watches(self):
        """

        :return:
        """
        return self._watches

    def teardown_watch(self):
        """
        Called when project deleted.

        :return:
        """

    def _produce_watch(self, symbol: EventSymbol) -> Watch:
        """

        :param event:
        :return:
        """
        proj = symbol.proj
        # proj type must be string type
        if not isinstance(proj, str):
            proj = str(proj)

        watch = Watch(proj)
        self.watches[proj] = watch
        return watch

    def _pull_event(self, symbol: EventSymbol, watch: Watch) -> 'Event':
        """

        :param event:
        :return:
        """
        event_type = symbol.event_type
        loop = self.loop
        if event_type not in HIVE_EVENTS:
            raise KeyError
        return HIVE_EVENTS[event_type](watch, symbol, loop)                        # type: ignore

    def queue_events(self, timeout: float) -> None:
        """

        :param timeout:
        :return:
        """
        # 삭제도 동기화를 시킬지 시키지 않을지 옵션으로 주기
        with self._lock:

            # Get local event symbol
            symbols = self.notify.read_events()

            # Get watch from watches dictionary by project name
            for symbol in symbols:
                watch = self.watches.get(symbol.proj, None)
                if not watch:
                    watch = self._produce_watch(symbol)

                try:
                    event: 'Event' = self._pull_event(symbol, watch)
                    print(event.event_type)
                    if not isinstance(event, t.Callable):                                     # type: ignore
                        raise TypeError

                    coroutine_event: t.Coroutine = event()
                    task = self._task_factory(coroutine_event)

                    self.queue_event((task, event))
                except Exception as e:
                    if isinstance(e, KeyError):
                        raise e
                    raise e

    def on_thread_stop(self):
        """
        Stop the notify processing
        """
        self.notify.stop()

    def on_thread_start(self):
        """

        :return:
        """
        if 'remotenotify_connector' not in self.params:
            self.params.update({"remotenotify_connector": self.connector_cls})

        self.notify = Notify(**self.params)


class HiveWatcher:

    def __init__(self,
                 host: str,
                 port: int,
                 watch_path: str,
                 loop_kind: str,
                 root_dir: str,
                 ignore_pattern: str,
                 proj_depth: int = 1,
                 timeout: t.Optional[float] = DEFAULT_QUEUE_TIMEOUT,
                 record_interval_minute: t.Optional[float] = 5,
                 max_event: t.Optional[int] = None
                 ):

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self._watches: t.Dict[str, Watch] = {}  # key: project, watch

        # queue get timeout
        self._timeout = timeout

        # notify parameter
        self.remotenotify_host = host
        self.remotenotify_port = port
        self.localnotify_root_dir = root_dir
        self.localnotify_ignore_pattern = ignore_pattern
        self.localnotify_proj_depth = proj_depth

        # loop kind
        self.loop_kind = loop_kind

        # watches record_interval
        self.record_interval_minute = record_interval_minute

        # exit flag
        self.should_exit = False

        # exit event
        self.exit_notify = threading.Event()

        # max event number
        # If event occur over the max event, restart watch continually
        self.max_event = max_event

        # storage place of watch information
        self.watch_path = watch_path

        # watch writer
        # Write the watches in files to protect the remote servers information
        # when watcher down
        self.watch_writer = WatchIO(self.watch_path, self._watches)

        # event count
        self.event_count = None

        # tasks
        self.tasks: t.Set[t.Tuple[Task, Event]] = set()

        # watcher start time
        self.start_time = time.time()

    def watch(self):
        _set_loop(self.loop_kind)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.run())

    async def run(self):

        await self.load_watch()

        self.install_signal_handlers()
        loop = asyncio.get_event_loop()
        emit = loop.create_task(self.emit())
        if self.should_exit:
            return

        await self.main_loop()
        await self.shutdown()

    async def emit(self):

        loop = asyncio.get_event_loop()
        event_queue = self._event_queue
        watches = self._watches
        timeout = self.timeout
        count = 0
        self.emitter = HiveEventEmitter(loop,
                                        event_queue,
                                        watches,
                                        loop.create_task,
                                        timeout,
                                        localnotify_root_dir=self.localnotify_root_dir,
                                        localnotify_ignore_pattern=self.localnotify_ignore_pattern,
                                        localnotify_proj_depth=self.localnotify_proj_depth,
                                        remotenotify_host=self.remotenotify_host,
                                        remotenotify_port=self.remotenotify_port)
        self.emitter.start()

        while not self.should_exit:
            try:
                # dequeue event
                task, event = self.get_event_queue()
                # Put event in task set
                self.tasks.add((task, event))

                # execute event
                await execute_event(task, event)

                if self.event_count is not None:
                    count += 1
                    self.event_count = count

            except queue.Empty:
                await asyncio.sleep(0)
                pass

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
                del task
            else:
                self.tasks.add((task, event))

        # Write watch information in files
        if now - self.start_time >= self.record_interval_minute*60:
            await self.watch_writer.record()
            self.start_time = now

        if self.should_exit:
            return True

        return False

    async def shutdown(self):
        """
        Shutting down watcher.
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

        # Record watches information.
        await self.watch_writer.record()

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

    async def load_watch(self):
        """
        Load watch information from files before start watcher.
        :return:
        """
        loop = asyncio.get_event_loop()
        await self.watch_writer.load(Watch, loop)

    async def record_watch(self):
        """

        :return:
        """
        await self.watch_writer.record()

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