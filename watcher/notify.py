import time
import queue
import threading
import selectors
import typing as t

from werkzeug.serving import ThreadedWSGIServer as WSGIServer

from .buffer import LocalBuffer
from .buffer import RemoteBuffer
from .buffer import EventSymbol

from watcher import BaseThread, EventQueue


if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector                                                 # type: ignore

_TSSLContextArg = t.Optional[
    t.Union["ssl.SSLContext", t.Tuple[str, t.Optional[str]], "te.Literal['adhoc']"]            # type: ignore
]

if t.TYPE_CHECKING:
    from .wrapper.response import WatcherConnector


EVENT_PERIOD = 0.5


class Notify:

    __notifies__: t.Set[t.Union['RemoteNotify', 'LocalNotify']] = set()

    def __init__(self, **params: t.Dict[str, t.Any]):
        self.params = params
        self.notifies = []

        for notify in self.__notifies__:
            noti_kwargs = {}
            notify_name = notify.__name__.lower()                                               # type: ignore
            for arg, value in self.params.items():
                seperated_arg = arg.split("_")

                cls_name = seperated_arg[0]

                arg_name = '_'.join(seperated_arg[1:])
                if notify_name == cls_name:
                    noti_kwargs[arg_name] = value

            buffer_queue: queue.Queue = queue.Queue()
            self.notifies.append(notify(buffer_queue=buffer_queue, **noti_kwargs))              # type: ignore

    @classmethod
    def register(cls, notify: t.Union[t.Any, 'LocalNotify', 'RemoteNotify']) -> None:
        """
        register
        :param notify:
        :return:
        """
        cls.__notifies__.add(notify)

    def read_events(self) -> t.List[EventSymbol]:

        symbols = []
        for notify in self.notifies:
            symbol = notify.read_event()
            symbols.append(symbol)

        return [symbol for symbol in symbols if isinstance(symbol, EventSymbol)]


class LocalNotify(BaseThread):
    """
    :param root_dir
    :param proj_depth
    :param ignore_pattern

    """
    def __init__(self,
                 root_dir: str,
                 proj_depth: int,
                 ignore_pattern: str,
                 buffer_queue: queue.Queue):
        super().__init__()

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self._buffer_queue = buffer_queue
        self._buffer = LocalBuffer(root_dir, proj_depth, ignore_pattern, buffer_queue)
        self.start()

    def read_event(self) -> EventSymbol:
        """
        :return:
        """
        try:
            q = self._event_queue.get(timeout=0.001)
        except queue.Empty:
            q = set()
        return q

    def queue_event(self, event):
        """
        :param event:
        :return:
        """
        self._event_queue.put(event)

    def run(self):
        """
        :return:
        """
        while self.should_keep_running():
            with self._lock:
                events = self._buffer.read_events()
                #time sleep for excluding tempfile
                for event in events:
                    self.queue_event(event)
            time.sleep(EVENT_PERIOD)


Notify.register(LocalNotify)


class RemoteNotify(BaseThread,  WSGIServer):

    def __init__(self,
                 host: str,
                 port: int,
                 connector: 'WatcherConnector',
                 buffer_queue: queue.Queue,
                 handler: t.Optional[t.Type["RemoteBuffer"]] = RemoteBuffer,
                 passthrough_errors: bool = False,
                 ssl_context: t.Optional[_TSSLContextArg] = None,
                 fd: t.Optional[int] = None,
                 ) -> None:

        BaseThread.__init__(self)


        app = None
        self.connector = connector

        WSGIServer.__init__(self,
                            host,
                            port,
                            app,
                            handler,
                            passthrough_errors,
                            ssl_context,
                            fd)

        self._lock = threading.RLock()
        self._event_queue = EventQueue()
        self._buffer_queue = buffer_queue
        self.start()

    @property
    def buffer_queue(self):
        return self._buffer_queue

    def serve_forever(self, poll_interval=0.5):
        try:
            WSGIServer.serve_forever(self)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def read_event(self) -> EventSymbol:
        """

        :return:
        """
        try:
            q = self._event_queue.get(timeout=0.001)
        except queue.Empty:
            q = ''
        return q

    def queue_event(self, event):
        """

        :param event:
        :return:
        """
        self._event_queue.put(event)

    def finish_request(self, request: 'Socket', client_address):                                 # type: ignore
        """Finish one request by instantiating RequestHandlerClass."""

        self.RequestHandlerClass(request, client_address, self)

    def read_buffer_event(self) -> t.Set[t.Any]:
        """
        :return:
        """
        events = set()
        is_empty = False
        while not is_empty:
            try:
                es = self.buffer_queue.get(timeout=0)
                events.add(es)
            except queue.Empty:
                is_empty = True

        return events

    def service_actions(self) -> None:
        """

        :return:
        """
        with self._lock:
            events = self.read_buffer_event()
            while events:
                event = events.pop()
                self.queue_event(event)

    def run(self):
        while self.should_keep_running():
            self.serve_forever()


Notify.register(RemoteNotify)

