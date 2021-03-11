

import time
import threading
import http.server
import selectors
import typing as t

from .buffer import LocalBuffer
from .buffer import RemoteBuffer
from watcher import BaseThread, EventQueue

if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector


EVENT_PERIOD = 0.5

class LocalNotifiy(BaseThread):
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
        return self._event_queue.get()

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



class RemoteNotifiy(BaseThread, http.server.HTTPServer):

    def __init__(self,
                 server_address):

        BaseThread.__init__(self)
        http.server.HTTPServer.__init__(server_address, RemoteBuffer)
        self._lock = threading.RLock()
        self._event_queue = EventQueue()
        self.start()


    def serve_forever(self, poll_interval=0.5):
        try:
            super().serve_forever(poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def read_event(self):
        """

        :return:
        """
        return self._event_queue.get()

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
        events = self._buffer.read_events()
        while events:
            event = events.pop()
            self.queue_event(event)

    def run(self):
        while self.should_keep_running():
            self.serve_forever()



