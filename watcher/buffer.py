import os
import re
import http
import time
import socket
import queue
import typing as t
import selectors
import threading

from watcher.common import EventStatus
from watcher.exceptions import FilePaserError

from werkzeug.serving import ThreadedWSGIServer as WSGIServer
from werkzeug.wrappers import Request as WSGIRequest
from werkzeug.serving import WSGIRequestHandler
from werkzeug.datastructures import EnvironHeaders
from werkzeug.wrappers import Response

from watcher.common import BaseThread, EventQueue

if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector                                                 # type: ignore

_TSSLContextArg = t.Optional[
    t.Union["ssl.SSLContext", t.Tuple[str, t.Optional[str]], "te.Literal['adhoc']"]            # type: ignore
]

if t.TYPE_CHECKING:
    from .wrapper.response import WatcherConnector


EVENT_TYPE_KEY = 'Event-Type'
PROJECT_KEY    = 'Project-Name'
EVENT_PERIOD = 0.5


class EventSymbol:

    def __init__(self,
                 proj: str,
                 event_type: t.Optional[t.Union[EventStatus, int]] = None):

        self.proj = proj
        self._event_type = event_type

    @property
    def event_type(self) -> t.Optional[t.Union[EventStatus, int]]:
        return self._event_type

    @property
    def key(self):
        raise NotImplementedError

    def __eq__(self, event) -> bool:
        return self.key == event.key

    def __ne__(self, event) -> bool:
        return self.key == event.key

    def __hash__(self):
        return hash(self.key)


class LocalEventSymbol(EventSymbol):

    # file 확장자 정보 담기
    def __init__(self,
                 proj: str,
                 path: str,
                 event_type: t.Optional[t.Union[EventStatus, int]] = None
                 ):
        super().__init__(proj, event_type)

        self.path = path
        if not self.parse_path(self.path):
            # message
            raise FilePaserError

    def parse_path(self, path: str) -> bool:
        """
        Function to pull the file extention
        :param path:
            file path
            ex)
                /user/defined/directory/file.ext
        :return:
            file extension
            ex)
                .txt, , .xml, .json etc..
        """

        entities = path.split("/")

        # Todo display log
        try:
            self.file_type = entities[-2]
            self.ext = os.path.splitext(path)[-1]

        except (IndexError, OSError):
            return False

        return True


    @property
    def key(self) -> t.Tuple[str, str]:
        #key에 status도 추가해야 하지 않을까????

        return self.proj, self.path

    def __eq__(self, event):
        return self.key == event.key

    def __ne__(self, event):
        return self.key == event.key

    def __hash__(self):
        return hash(self.key)


class RemoteEventSymbol(EventSymbol):

    # 나중에 서버 바꾸자..

    def __init__(self,
                 proj: str,
                 environ: t.Dict[str, t.Any],
                 connector: 'WatcherConnector',                                                  # type: ignore
                 event_type: t.Optional[t.Union[EventStatus, int]] = None
                 ):

        super().__init__(proj, event_type)

        self.environ = environ
        self.request = WSGIRequest(environ)
        self.connector = connector

        if event_type is None:
            self._event_type = int(self.headers.get('Event-Type'))                                # type: ignore

    @property
    def event_type(self) -> t.Optional[t.Union[EventStatus, int]]:
        """
        Propery of event type
        :return:
            event type
        """
        return self._event_type

    @property
    def client_host(self) -> str:
        """
        Client host property
        :return:
            Make host into a sagging shape
            example)
                0.0.0.0:8080
        """
        host, _ = self.client_address.split(":")
        return host                                        # type: ignore

    @property
    def headers(self) -> 'EnvironHeaders':
        """
        Property of request header
        :return:
        """

        return self.request.headers

    @property
    def client_address(self) -> str:
        """

        :return:
        """
        addr = self.environ.get("HTTP_CLIENT_ADDRESS")
        scheme = self.environ.get("wsgi.url_scheme", None)
        if scheme is None:
            scheme = 'http'
        if not isinstance(addr, str):
            addr = str(addr)
        url = f'{scheme}://{addr}'
        return url

    @property
    def client_port(self) -> str:
        """

        :return:
        """
        _, port = self.client_address.split(":")
        if not isinstance(port, str):
            port = str(port)

        return port

    @property
    def key(self) -> t.Tuple[str, str]:
        # key에 status도 추가해야 하지 않을까????

        return self.proj, self.client_address


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
        Method to register notifies.
        :param notify:

        """
        cls.__notifies__.add(notify)

    def read_events(self) -> t.List[EventSymbol]:
        """
        Method to read the event from symbols.
        """

        symbols = []
        for notify in self.notifies:
            symbol = notify.read_event()
            symbols.append(symbol)
        return [symbol for symbol in symbols if isinstance(symbol, EventSymbol)]

    def stop(self):
        """
        Method to stop Notify.
        """
        for notify in self.notifies:
            notify.stop()


class LocalBuffer:
    """
    ignore pattern is regex_pattern
    """
    def __init__(self,
                 root_path: str,
                 proj_depth: int,
                 ignore_pattern: str,
                 buffer_queue: queue.Queue,
                 files: t.Dict[str, t.Tuple[str, float]]):

        self._root_path = root_path
        self._project_depth = proj_depth
        self.buffer_queue = buffer_queue
        self.files: t.Dict[str, t.Tuple[str, float]] = files
        self.ignore_pattern = ignore_pattern

    @property
    def root_path(self) -> str:
        return self._root_path

    @property
    def proj_depth(self) -> int:
        return self._project_depth

    def _knock_dir(self,
                   path: str,
                   symbols: queue.Queue,
                   new_files: t.Dict[str, t.Tuple[str, float]],
                   depth: int,
                   proj: str = 'base'):

        # 코드 다시 고려해보기
        if depth == self.proj_depth:
            proj = os.path.basename(path)
        depth += 1

        for entry in os.scandir(path):
            if entry.is_dir():
                self._knock_dir(entry.path, symbols, new_files, depth, proj)
            else:
                filename = os.path.basename(entry.path)
                if re.match(self.ignore_pattern, filename):
                    continue
                self._knock_file(entry.path, symbols, new_files, entry.stat(), proj)
        depth -= 1

    def _knock_file(self,
                    path: str,
                    symbols: queue.Queue,
                    new_files: t.Dict[str, t.Tuple[str, float]],
                    stat: os.stat_result,
                    proj: str = 'base'): #default 이름 정하

        new_mtime = stat.st_mtime
        new_files[path] = (proj, new_mtime)
        old_proj, old_mtime = self.files.get(path, (None, None))

        if not old_mtime:
            symbols.put(LocalEventSymbol(proj,
                                         path,
                                         EventStatus.FILE_CREATED))
        elif new_mtime != old_mtime:
            symbols.put(LocalEventSymbol(proj,
                                         path,
                                         EventStatus.FILE_MODIFIED))

    def _knock(self,
               path: str,
               symbols: queue.Queue,
               new_files: t.Dict[str, t.Tuple[str, float]],
               depth: int):

        if os.path.isdir(path):
            self._knock_dir(path, symbols, new_files, depth)
        else:
            self._knock_file(path, symbols, new_files, os.stat(path))

    def _delete_file(self, file):
        self.files.pop(file)

    def read_events(self):
        """

        :return:
        """
        self.run_events()
        events = set()
        is_empty = False
        while not is_empty:
            try:
                es = self.buffer_queue.get(timeout=0)
                events.add(es)
            except queue.Empty:
                is_empty = True
        return events

    def run_events(self):
        symbols = self.buffer_queue
        new_files: t.Dict[str, t.Tuple[str, float]] = {}
        depth = 0
        try:
            self._knock(self._root_path, symbols, new_files, depth)
        except OSError as e:
            #Todo log 찍어야함
            raise e

        # Find deleted files
        deleted_files = self.files.keys() - new_files.keys()
        for path in deleted_files:
            proj = self.files[path][0]
            symbols.put(LocalEventSymbol(proj, path, EventStatus.FILE_DELETED))
            self._delete_file(path)

        # Files updated with new content
        self.files.update(new_files)


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
                 buffer_queue: queue.Queue,
                 files: t.Dict[str, t.Tuple[str, float]]):
        super().__init__()

        self._lock = threading.Lock()
        self._event_queue = EventQueue()
        self._buffer_queue = buffer_queue
        self._buffer = LocalBuffer(root_dir, proj_depth, ignore_pattern, buffer_queue, files)
        self.start()

    def read_event(self) -> EventSymbol:
        """
        Method to get event out from event queue.
        """
        try:
            q = self._event_queue.get(timeout=0.001)
        except queue.Empty:
            q = set()
        return q

    def queue_event(self, event):
        """
        Method to queue event into event_queue.
        :param event:
            Event to be enqueued.
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


class RemoteBuffer(WSGIRequestHandler):

    # header()
    # get_data()
    # router 어떻게 시킬지

    def __init__(self,
                 request: 'Socket',                                                           # type: ignore
                 client_address: t.Tuple[str, int],
                 server: 'RemoteNotify'):                                                     # type: ignore
        self.buffer_queue = server.buffer_queue
        super().__init__(request, client_address, server)

    @property
    def project_name(self) -> str:
        """
        Property of project name
        :return:
            Project name
        """
        return self.headers.get(PROJECT_KEY)

    def run_event(self):
        """

        :return:
        """
        self.server.app = self.connector = self.server.connector(Response)
        self.environ = self.make_environ()
        self.buffer_queue.put(RemoteEventSymbol(self.project_name, self.environ, self.connector))

        super().run_wsgi()

    def parse_request(self) -> bool:
        base_output = super().parse_request()

        event_type = self.headers.get(EVENT_TYPE_KEY, None)
        project_name = self.headers.get(PROJECT_KEY, None)

        if not event_type or not project_name:
            if not event_type and project_name:
                message = '%s key' % EVENT_TYPE_KEY
            elif event_type and not project_name:
                message = '%s key' % PROJECT_KEY
            else:
                message = '%s, %s keys' % (PROJECT_KEY, EVENT_TYPE_KEY)
            self.send_error(
                http.HTTPStatus.BAD_REQUEST,
                "Bad request header. "
                "Header must contain (%s) " % message)
            return False
        return base_output

    def handle_one_request(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if self.parse_request():
                self.run_event()
        except (ConnectionError, socket.timeout) as e:
            self._connection_dropped(e)
        except Exception as e:
            self.log_error("error: %s, ", e.__class__.__name__, e.args[0])

    def _connection_dropped(self, error: Exception) -> None:
        """
        Called if the connection is closed by the client
        :param error:
        """
        pass


class DummyBuffer:

    def read_events(self):
        return set()


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
        """
        Buffer queue property
        """
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
        Method to read event from  queue.
        """
        try:
            q = self._event_queue.get(timeout=0.001)
        except queue.Empty:
            q = ''
        return q

    def queue_event(self, event):
        """
        Method to enqueue event into event_queue.
        :param event:
            Event
        """
        self._event_queue.put(event)

    def finish_request(self, request: 'Socket', client_address):                                 # type: ignore
        """Finish one request by instantiating RequestHandlerClass."""

        self.RequestHandlerClass(request, client_address, self)

    def read_buffer_event(self) -> t.Set[t.Any]:
        """
        Method to read event from buffer queue.
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
        Method to read event from buffer queue and enqueue
        event into even queue.
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
