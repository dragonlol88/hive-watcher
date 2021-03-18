import os
import re
import http
import socket
import typing as t

from watcher import EventStatus
from watcher.exceptions import FilePaserError

from werkzeug.wrappers import Request as WSGIRequest
from werkzeug.serving import WSGIRequestHandler

# buffer 단에서
# local event 와 remote event의 공통사항을 묶을 수 있는 interface 하나 정의하자
# 이듦도 다시 짓자

EVENT_TYPE_KEY = 'Event-Type'
PROJECT_KEY    = 'Project-Name'


class EventSymbol:

    def __init__(self,
                 proj: str,
                 event_type: t.Optional[t.Union['enum', int]] = None):

        self.proj = proj
        self._event_type = event_type

    @property
    def event_type(self) -> int:
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
                 event_type: 'enum'):
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
        #Todo display log
        try:
            self.file_type = entities[-2]
            if self.file_type not in ('synonym', 'userdict', 'stopword', 'index'):
                return False

            self.ext = os.path.splitext(path)[-1]
            if self.ext not in ('.txt', '.json', '.xlsx'):
                return False

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
                 environ: t.Dict[str, t.Any]
                 ):

        super().__init__(proj)

        self.environ = environ
        self.request = WSGIRequest(environ)

    @property
    def event_type(self) -> int:
        """
        Propery of event type
        :return:
            event type
        """
        return int(self.headers.get('Event-Type'))

    @property
    def client_host(self) -> str:
        """
        Client host property
        :return:
            Make host into a sagging shape
            example)
                0.0.0.0:8080
        """
        scheme = self.environ.get("wsgi.url_scheme")
        client_address = self.client_address, self.client_port
        return scheme + "://" + ":".join(client_address)

    @property
    def headers(self) -> t.Dict[str, t.Any]:
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
        addr = self.environ.get("REMOTE_ADDR")
        if not isinstance(addr, str):
            addr = str(addr)
        return addr

    @property
    def client_port(self) -> str:
        """

        :return:
        """
        port = self.environ.get("REMOTE_PORT")
        if not isinstance(port, str):
            port = str(port)

        return port

    @property
    def key(self) -> t.Tuple[str, str]:
        # key에 status도 추가해야 하지 않을까????

        return self.proj, self.client_address


class LocalBuffer:

    def __init__(self,
                 root_path: str,
                 proj_depth: int,
                 ignore_pattern: 'regex pattern'):

        self._root_path = root_path
        self._project_depth = proj_depth
        self.files: t.Dict[str, float] = {}
        self.ignore_pattern = ignore_pattern

    @property
    def root_path(self):
        return self._root_path

    @property
    def proj_depth(self):
        return self._project_depth

    def _knock_dir(self,
                   path: str,
                   events: t.Set[LocalEventSymbol],
                   new_files: t.Dict[str, t.Tuple[str, float]],
                   depth: int,
                   proj: t.Optional[str]=None):

        # 코드 다시 고려해보기
        if depth == self.proj_depth:
            proj = os.path.basename(path)
        depth += 1

        for entry in os.scandir(path):
            if entry.is_dir():
                self._knock_dir(entry.path, events, new_files, depth, proj)
            else:
                filename = os.path.basename(entry.path)
                if re.match(self.ignore_pattern, filename):
                    continue
                self._knock_file(entry.path, events, new_files, entry.stat(), proj)
        depth -= 1

    def _knock_file(self,
                    path: str,
                    events: t.Set[LocalEventSymbol],
                    new_files: t.Dict[str, t.Tuple[str, float]],
                    stat: os.stat,
                    proj: str):

        new_mtime = stat.st_mtime
        new_files[path] = (proj, new_mtime)
        old_proj, old_mtime = self.files.get(path, (None, None))

        if not old_mtime:
            events.add(LocalEventSymbol(proj,
                                        path,
                                        EventStatus.FILE_CREATED))
        elif new_mtime != old_mtime:
            events.add(LocalEventSymbol(proj,
                                        path,
                                        EventStatus.FILE_MODIFIED))

    def _knock(self,
               path: str,
               events: t.Set[LocalEventSymbol],
               new_files: t.Dict[str, t.Tuple[str, float]],
               depth: int):

        if os.path.isdir(path):
            self._knock_dir(path, events, new_files, depth)
        else:
            self._knock_file(path, events, new_files, os.stat(path))

    def read_events(self):
        events: t.Set[LocalEventSymbol] = set()
        new_files: t.Dict[str, t.Dict[str, float]] = {}
        depth = 0
        try:
            self._knock(self._root_path, events, new_files, depth)
        except OSError as e:
            #Todo log 찍어야함
            raise e

        deleted_files = self.files.keys() - new_files.keys()

        if deleted_files:
            events |= {LocalEventSymbol(self.files[deleted_file][0],
                                        deleted_file,
                                        EventStatus.FILE_DELETED)
                       for deleted_file in deleted_files}
        #Todo file 저장하는거 코드 추
        self.files = new_files

        return events


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

    events = set()
    # header()
    # get_data()
    # router 어떻게 시킬지

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    @property
    def project_name(self) -> str:
        """
        Property of project name
        :return:
            Project name
        """
        return self.headers.get(PROJECT_KEY)

    def read_events(self):
        """
        :return:
        """
        cur_event = set()
        for _ in range(len(self.events)):
            cur_event.add(self.events.pop())

        return cur_event

    def run_event(self):
        """

        :return:
        """
        super().run_wsgi()
        self.events.add(RemoteEventSymbol(self.project_name, self.environ))

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