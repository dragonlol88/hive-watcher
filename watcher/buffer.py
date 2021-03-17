import os
import re
import http
import socket
import typing as t

from watcher import EventStatus
from watcher.exceptions import FilePaserError
# buffer 단에서
# local event 와 remote event의 공통사항을 묶을 수 있는 interface 하나 정의하자
# 이듦도 다시 짓자


class EventSymbol:

    def __init__(self,
                 proj: str,
                 event_type: 'enum'):

        self.proj = proj
        self.event_type = event_type

    @property
    def key(self):
        raise NotImplementedError

    def __eq__(self, event):
        return self.key == event.key

    def __ne__(self, event):
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
            #message
            raise FilePaserError

    def parse_path(self, path):
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
    def is_modified(self):
        return self.event_type - EventStatus.FILE_MODIFIED == 0

    @property
    def is_deleted(self):
        return self.event_type - EventStatus.FILE_DELETED == 0

    @property
    def is_created(self):
        return self.event_type - EventStatus.FILE_CREATED == 0

    @property
    def key(self):
        #key에 status도 추가해야 하지 않을까????

        return self.proj, self.path



    def __eq__(self, event):
        return self.key == event.key

    def __ne__(self, event):
        return self.key == event.key

    def __hash__(self):
        return hash(self.key)


class RemoteEventSymbol(EventSymbol):

    def __init__(self,
                 proj: str,
                 hosts: str,
                 event_type: 'enum'):

        self.proj = proj
        self.hosts = hosts
        self.event_type = event_type

    def is_close(self):
        """

        :return:
        """
        return self.event_type - EventStatus.DELETE_CHANNEL == 0

    def is_connect(self):
        """

        :return:
        """
        return self.event_type - EventStatus.CREATE_CHANNEL == 0


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
#    "level": ""
#}

#client close # DELETE
#{
#    "prject": "",
#    "level": ""
#}

class RemoteBuffer(http.server.BaseHTTPRequestHandler):

    event = set()
    # header()
    # get_data()
    # router 어떻게 시킬지

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def read_events(self):
        """

        :return:
        """
        return self.events

    def run_event(self):
        """

        :return:
        """

        pass

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





