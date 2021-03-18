import time
import queue
import threading
import selectors
import typing as t

from werkzeug.serving import BaseWSGIServer as WSGIServer
from werkzeug.wrappers import Response

from .buffer import LocalBuffer
from .buffer import RemoteBuffer
from .buffer import DummyBuffer
from .buffer import EventSymbol

from watcher import BaseThread, EventQueue

if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector

_TSSLContextArg = t.Optional[
    t.Union["ssl.SSLContext", t.Tuple[str, t.Optional[str]], "te.Literal['adhoc']"]
]

EVENT_PERIOD = 0.5


class Notify:

    __notifies__ = set()

    def __init__(self, **kwargs):

        self.params = kwargs
        self.notifies = []

        for notify in self.__notifies__:
            noti_kwargs = {}
            notify_name = notify.__name__.lower()
            for arg, value in self.params.items():
                seperated_arg = arg.split("_")

                cls_name = seperated_arg[0]

                arg_name = '_'.join(seperated_arg[1:])
                if notify_name == cls_name:
                    noti_kwargs[arg_name] = value
            self.notifies.append(notify(**noti_kwargs))

    @classmethod
    def register(cls, notify):
        """
        register
        :param notify:
        :return:
        """
        cls.__notifies__.add(notify)

    def read_events(self):

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
                 ignore_pattern: 'regex_pattern'):
        super().__init__()

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self._buffer = LocalBuffer(root_dir, proj_depth, ignore_pattern)
        self.start()

    def read_event(self):
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


class RemoteNotify(BaseThread, WSGIServer):

    def __init__(self,
                 host: str,
                 port: int,
                 app: t.Optional["WSGIApplication"] = None,
                 handler: t.Optional[t.Type["RemoteBuffer"]] = RemoteBuffer,
                 passthrough_errors: bool = False,
                 ssl_context: t.Optional[_TSSLContextArg] = None,
                 fd: t.Optional[int] = None,
                 ) -> None:

        BaseThread.__init__(self)

        if app is None:
            # response....
            app = Response("hello response ok")

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
        self.initialize_buffer()
        self.start()

    def initialize_buffer(self):
        """

        :return:
        """
        self._buffer = DummyBuffer()

    def serve_forever(self, poll_interval=0.5):
        try:
            WSGIServer.serve_forever(self)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def read_event(self):
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

    def finish_request(self, request, client_address):
        """Finish one request by instantiating RequestHandlerClass."""

        self._buffer = self.RequestHandlerClass(request, client_address, self)

    def service_actions(self) -> None:
        """

        :return:
        """
        with self._lock:
            events = self._buffer.read_events()
            while events:
                event = events.pop()
                self.queue_event(event)

            self.initialize_buffer()

    def run(self):
        while self.should_keep_running():
            self.serve_forever()


Notify.register(RemoteNotify)

