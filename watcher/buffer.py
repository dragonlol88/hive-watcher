import os
import re
import http
import socket
import queue
import typing as t

from watcher import EventStatus
from watcher.exceptions import FilePaserError

from werkzeug.wrappers import Request as WSGIRequest
from werkzeug.serving import WSGIRequestHandler
from werkzeug.datastructures import EnvironHeaders
from werkzeug.wrappers import Response

EVENT_TYPE_KEY = 'Event-Type'
PROJECT_KEY    = 'Project-Name'


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
        scheme = self.environ.get("wsgi.url_scheme")
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


class LocalBuffer:
    """
    ignore pattern is regex_pattern
    """
    def __init__(self,
                 root_path: str,
                 proj_depth: int,
                 ignore_pattern: str,
                 buffer_queue: queue.Queue):

        self._root_path = root_path
        self._project_depth = proj_depth
        self.buffer_queue = buffer_queue
        self.files: t.Dict[str, t.Tuple[str,float]] = {}
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

        deleted_files = self.files.keys() - new_files.keys()

        if deleted_files:
            for deleted_file in deleted_files:
                symbols.put(LocalEventSymbol(self.files[deleted_file][0],
                                        deleted_file,
                                        EventStatus.FILE_DELETED))

        #Todo file 저장하는거 코드 추
        self.files = new_files



#client connection # POST
#{
#    "project": "",
#    "event_type":"",
#    "level": ""
#}

#client close # DELETE
#{
#    "prject": "",
#    "event_type":"",
#    "level": ""
#}

# rfile 읽어오는 stream
# route 어떻게 시킬까? url,
#


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

    # def read_events(self) -> t.Set[RemoteEventSymbol]:
    #     """
    #     :return:
    #     """
    #     events = set()
    #     is_empty = False
    #     while not is_empty:
    #         try:
    #             es = self.buffer_queue.get(timeout=0)
    #             events.add(es)
    #         except queue.Empty:
    #             is_empty = True
    #     return events

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