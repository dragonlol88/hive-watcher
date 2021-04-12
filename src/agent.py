import os
import re
import http
import time
import socket
import queue
import typing as t
import selectors
import threading

from werkzeug.serving import ThreadedWSGIServer as WSGIServer
from werkzeug.wrappers import Request as WSGIRequest
from werkzeug.serving import WSGIRequestHandler
from werkzeug.datastructures import EnvironHeaders
from werkzeug.wrappers import Response

from .common import BaseThread
from .common import EventSentinel

if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector                                                 # type: ignore

_TSSLContextArg = t.Optional[
    t.Union["ssl.SSLContext", t.Tuple[str, t.Optional[str]], "te.Literal['adhoc']"]            # type: ignore
]

if t.TYPE_CHECKING:
    from src.wrapper import WatcherConnector


EVENT_TYPE_KEY = 'Event-Type'
PROJECT_KEY    = 'Project-Name'
EVENT_PERIOD = 0.5




class AgentHandler(WSGIRequestHandler):

    def __init__(self,
                 request: 'Socket',                                                           # type: ignore
                 client_address: t.Tuple[str, int],
                 server: 'Agent'):                                                            # type: ignore
        WSGIRequestHandler.__init__(self, request, client_address, server)
        self.event_queue = self.server.event_queue
        self.event_type = None
        self.project_name = None

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
        self.event_type = event_type
        self.project_name = project_name
        return base_output

    def handle_one_request(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if self.parse_request():
                self.run_wsgi()
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

    @property
    def channel(self) -> str:
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

    def run_wsgi(self):
        """
        :return:
        """

        #self.server.app = self.connector = self.server.connector(Response)

        self.environ = self.make_environ()

        if self.event_type == EventSentinel.CREATE_CHANNEL:
            self.event_queue.put(
                (self.project_name, EventSentinel.CREATE_CHANNEL, self.channel))
        elif self.event_type == EventSentinel.DELETE_CHANNEL:
            self.event_queue.put(
                (self.project_name, EventSentinel.DELETE_CHANNEL, self.channel))
        elif self.event_type in (
                    EventSentinel.FILE_MODIFIED,
                    EventSentinel.CREATE_CHANNEL,
                    EventSentinel.FILE_DELETED):
            self.server.app = Response(b"")
        else:
            pass
        self.server.app = Response(b"")
        super().run_wsgi()


class Agent(BaseThread,  WSGIServer):

    def __init__(self,
                 host: str,
                 port: int,
                 event_queue: queue.Queue,
                 handler: t.Optional[t.Type["AgentHandler"]] = AgentHandler,
                 passthrough_errors: bool = False,
                 ssl_context: t.Optional[_TSSLContextArg] = None,
                 fd: t.Optional[int] = None,
                 ) -> None:

        BaseThread.__init__(self)
        app = None
        WSGIServer.__init__(self,
                            host,
                            port,
                            app,
                            handler,
                            passthrough_errors,
                            ssl_context,
                            fd)

        self._lock = threading.RLock()
        self.event_queue = event_queue
        self.start()

    def serve_forever(self, poll_interval=0.5):
        try:
            WSGIServer.serve_forever(self)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def finish_request(self, request: 'Socket', client_address):                                 # type: ignore
        """Finish one request by instantiating RequestHandlerClass."""
        self.RequestHandlerClass(request, client_address, self)

    def run(self):
        while self.should_keep_running():
            self.serve_forever()