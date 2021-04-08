import asyncio
import threading
import inspect
import typing as t

from src.buffer import EventSymbol
from src.buffer import Notify

from .common import BaseThread
from .common import EventQueue
from .events import HIVE_EVENTS
from .type import Task
from .wrapper.response import WatcherConnector

if t.TYPE_CHECKING:
    from src.events import EventBase as Event


class _Emitter(BaseThread):
    """
    :param loop
    :param event_queue
    :param timeout

    """

    def __init__(self):
        BaseThread.__init__(self)
        self._event_queue = EventQueue()


    def queue_event(self, item: t.Tuple['Task', 'Event']):
        """
        Queues a single event.

        :param item:
            Event to be queued.
            event: <class:awatcher.events.*>
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
        Method to q
        """
        while self.should_keep_running():
            self.queue_events(self.timeout)


class EventEmitter(_Emitter):
    connector_cls = WatcherConnector

    def __init__(self,
                 watcher,
                 event_queque,
                 loop,
                 **params):
        _Emitter.__init__(self)

        self._lock = threading.Lock()
        self._loop = loop
        self.watcher = watcher
        self._event_queue = event_queque
        self.params = params
        self.tasks = {}

    @property
    def loop(self):
        return self._loop

    @property
    def transporter(self):
        return self.watcher.transporter

    @property
    def timeout(self):
        """
        Blocking timeout for reading events.
        """
        return self.watcher._timeout

    @property
    def manager_pool(self):
        return self.watcher.manager_pool

    def _pull_event(self, symbol: EventSymbol, manager) -> 'Event':

        loop = self.loop
        transporter = self.transporter
        transporter.set_manager(manager)
        return HIVE_EVENTS[symbol.event_type](manager, transporter, symbol, loop)  # type: ignore

    def queue_events(self, timeout: float) -> None:

        # 삭제도 동기화를 시킬지 시키지 않을지 옵션으로 주기
        with self._lock:

            # Get local event symbol
            symbols = self.notify.read_events()

            # Get watch from watches dictionary by project name
            while symbols:
                symbol = symbols.pop()
                manager = self.manager_pool.get_manager(symbol)
                event = self._pull_event(symbol, manager)
                try:
                    aws = self.loop.create_task(event())
                except TypeError:
                    if not (asyncio.iscoroutine(event()) or \
                            inspect.isfunction(event)):
                        continue
                    aws = self.loop.run_in_executor(None, event)  # type: ignore
                self.queue_event((aws, event))

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