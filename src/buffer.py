import os
import re
import queue
import typing as t
import selectors

from . import common as c

if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector                                                 # type: ignore

_TSSLContextArg = t.Optional[
    t.Union["ssl.SSLContext", t.Tuple[str, t.Optional[str]], "te.Literal['adhoc']"]            # type: ignore
]

EVENT_TYPE_KEY = 'Event-Type'
PROJECT_KEY    = 'Project-Name'


FILE_CREATED   = c.EventSentinel.FILE_CREATED
FILE_DELETED   = c.EventSentinel.FILE_DELETED
FILE_MODIFIED  = c.EventSentinel.FILE_MODIFIED


class Sentinel:
    """
    ignore pattern is regex_pattern
    """
    def __init__(self,
                 root_path: str,
                 project_depth: int,
                 ignore_pattern: str,
                 files: t.Dict[str, t.Tuple[str, float]]):

        super().__init__()
        self.root_path = root_path
        self.project_depth = project_depth
        self.files = files
        self.ignore_pattern = ignore_pattern
        self.events = set()

    def _knock_dir(self,
                   path: str,
                   new_files: t.Dict[str, t.Tuple[str, float]],
                   depth: int,
                   proj: str = 'base'):

        # 코드 다시 고려해보기
        if depth == self.project_depth:
            proj = os.path.basename(path)
        depth += 1

        for entry in os.scandir(path):
            if entry.is_dir():
                self._knock_dir(entry.path, new_files, depth, proj)
            else:
                filename = os.path.basename(entry.path)
                if re.match(self.ignore_pattern, filename):
                    continue
                self._knock_file(entry.path, new_files, entry.stat(), proj)
        depth -= 1

    def _knock_file(self,
                    path: str,
                    new_files: t.Dict[str, t.Tuple[str, float]],
                    stat: os.stat_result,
                    proj: str = 'base'): #default 이름 정하

        new_mtime = stat.st_mtime
        new_files[path] = (proj, new_mtime)
        old_proj, old_mtime = self.files.get(path, (None, None))
        if not old_mtime:
            self.events.add((proj, path, FILE_CREATED))
        elif new_mtime != old_mtime:
            self.events.add((proj, path, FILE_MODIFIED))

    def _knock(self,
               path: str,
               new_files: t.Dict[str, t.Tuple[str, float]],
               depth: int):

        if os.path.isdir(path):
            self._knock_dir(path, new_files, depth)
        else:
            self._knock_file(path, new_files, os.stat(path))

    def run_buffer_once(self):
        new_files: t.Dict[str, t.Tuple[str, float]] = {}
        depth = 0
        try:
            self._knock(self.root_path, new_files, depth)
        except OSError as e:
            #Todo log 찍어야함
            raise e

        # Find deleted files
        deleted_files = self.files.keys() - new_files.keys()
        for path in deleted_files:
            proj = self.files[path][0]
            self.events.add((proj, path, FILE_DELETED))
            self.files.pop(path)

        # Files updated with new content
        self.files.update(new_files)

    def read_event(self):
        self.run_buffer_once()

        try:
            return self.events.pop()
        except KeyError:
            pass


class EventNotify(c.BaseThread):

    def __init__(self,
                 config,
                 event_queue: queue.Queue):
        super().__init__()

        self.root_dir = config.lookup_dir
        self.project_depth = config.project_depth
        self.ignore_pattern = config.ignore_pattern
        self.files = config.files
        self.event_queue = event_queue
        self._sentinel = Sentinel(self.root_dir, self.project_depth,
                                  self.ignore_pattern, self.files)
        self.start()

    def queue_event(self, event):
        """
        Method to queue event into event_queue.
        :param event:
            Event to be enqueued.
        """
        self.event_queue.put(event)

    def run(self):
        while self.should_keep_running():
            is_event_occur = True
            while is_event_occur:
                event = self._sentinel.read_event()
                if event is None:
                    is_event_occur = False
                else:
                    self.queue_event(event)
