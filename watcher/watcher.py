import asyncio
import threading
import functools
import typing as t

from watcher import BaseThread
from watcher import EventQueue

from .notify import Notify
from .events import HIVE_EVENTS
from .buffer import EventSymbol
from .type import Loop, Task
from .wrapper.response import WatcherConnector


DEFAULT_QUEUE_TIMEOUT = 1
partial = lambda : functools.partial


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
        self._channels: t.Set[str] = set() #{"http://192.168.0.230:5111/" "http://192.168.0.230:5112/
        self._loop = loop
        self._lock = asyncio.Lock(loop=loop)

    @property
    def paths(self) -> t.Set[str]:
        """
        The path that this watch monitors.
        """
        return self._paths

    @property
    def channels(self) -> t.Set[str]:
        """
        The channels that this watch monitors.
        """
        return self._channels

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
    :param root_dir
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

    def queue_event(self, event: 'Event'):                                                    # type: ignore
        """
        Queues a single event.

        :param event:
            Event to be queued.
            event: <class:watcher.events.*>
        """
        self._event_queue.put(event)

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

        watch = Watch(proj,
                      self._lock_factory)
        self.watches[proj] = watch
        return watch

    def _pull_event(self, symbol: EventSymbol, watch: Watch) -> 'Event':                      # type: ignore
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

            #Get watch from watches dictionary by project name
            for symbol in symbols:
                watch = self.watches.get(symbol.proj, None)
                if not watch:
                    watch = self._produce_watch(symbol)

                try:
                    event = self._pull_event(symbol, watch)
                    print(event.event_type)
                    if not asyncio.iscoroutine(event) and \
                            isinstance(event, t.Callable):                                    # type: ignore
                        event = event()

                    task = self._task_factory(event)
                    self.queue_event(task)
                except Exception as e:
                    if isinstance(e, KeyError):
                        raise e
                    raise e

    def on_thread_start(self):
        """

        :return:
        """
        if 'remotenotify_connector' not in self.params:
            self.params.update({"remotenotify_connector": self.connector_cls})

        self.notify = Notify(**self.params)

#
# class HiveWatcher:
#
#     def __init__(self,
#                  target_dir,
#                  server_ip='localhost',
#                  server_port=8080,
#                  queue_timeout=None):
#
#
#         lock = threading.RLock()
#         event_queue = EventQueue()
#
#         self.target_dir = target_dir
#         self._lock = lock
#         self._event_queue = event_queue
#         self._watches = {}  # key: project, watch
#         self._timeout = queue_timeout or DEFAULT_QUEUE_TIMEOUT
#
#         self.init_watch()
#
#     def run(self):
#         pass
#
#     def add_watch(self, event_queue, timeout):
#         event = event_queue.get(block=True, timeout=timeout)
#         with self._lock:
#             pass
#
#     def init_watch(self):
#         #dir 평가 어떻게??
#         walk = os.walk(self.target_dir)
#         for top, subs, files in walk:
#             if top == self.target_dir:
#                 self._watches = {sub: Watch(sub) for sub in subs}
#                 continue
#             proj = os.path.basename(top)
#             watch = self._watches[proj]
#             list(map(lambda file: watch.add_path(file), files))
#
#     @property
#     def event_queue(self):
#         return self._event_queue
#
#     @property
#     def timeout(self):
#         return self._timeout
#
