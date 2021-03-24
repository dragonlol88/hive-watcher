import io
import os
import json
import socket
import threading
import typing as t
import http.server
import http.client
from enum import IntEnum
from werkzeug.wsgi import LimitedStream
from werkzeug.serving import DechunkedInput

frost_server_address = ('127.0.0.1', 8132)
blaze_server_address = ('127.0.0.1', 8888)
watcher_server_address = ('127.0.0.1', 7777)
METHODS = ('POST', 'DELETE')
scheme = 'http'

class EventStatus(IntEnum):
    FILE_DELETED   = 1
    FILE_CREATED   = 2
    FILE_MODIFIED  = 3
    CREATE_CHANNEL = 4
    DELETE_CHANNEL = 5

def get_response(buffer: t.Union[io.IOBase, socket.socket], header: t.Dict[str, str]) -> 'Response':
    """

    :param buffer:
        File like object
    :param header:
        HTTP headers
    """

    if not isinstance(buffer, io.IOBase):
        buffer = buffer.makefile('rb', io.DEFAULT_BUFFER_SIZE)
    return Response(buffer, header)


def get_content_length(headers: t.Dict[str, str]) -> t.Optional[int]:
    """

    :param headers:
        HTTP headers
    """
    if 'Content-Length' in headers:
        return int(headers.get('Content-Length'))
    return


def get_stream(stream: t.BinaryIO, headers: t.Dict[str, str], safe_fallback: bool = True) -> t.BinaryIO:
    """

    :param stream:
        File like object
    :param headers:
        HTTP headers
    :param safe_fallback:
        When no conditions are satisfied, return raw stream binary io
    :return:
    """

    content_length = get_content_length(headers)
    if 'Transfer-Encoding' in headers:
        return DechunkedInput(stream)
    if content_length is None:
        return io.BytesIO if safe_fallback else stream
    return t.cast(t.BinaryIO, LimitedStream(stream, content_length))


class HTTPServer(http.server.HTTPServer):

    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)



class TestHandler(http.server.BaseHTTPRequestHandler):

    # HTTP headers
    headers: t.Dict[str, str]

    # response
    body = {
        "status": "",
        "event_type": ""
    }

    def __init__(self, request, client_address, server: HTTPServer):
        super().__init__(request, client_address, server)


    def run_event(self):

        headers = self.headers
        buffer = self.rfile
        status_set: t.Optional[str] = None
        headers_set: t.Optional[t.List[t.Tuple[str, str]]] = None
        status_sent: t.Optional[str] = None
        headers_sent: t.Optional[t.List[t.Tuple[str, str]]] = None
        event_type = headers['Event-Type']
        request_sucess = True
        body = self.body.copy()

        def write(data: bytes) -> None:

            nonlocal headers_sent, status_sent
            assert status_set is not None
            assert headers_set is not None


            if not status_sent:

                status_sent = status_set
                headers_sent = headers_set

                try:
                    code_str, msg = status_sent.split(None, 1)
                except ValueError:
                    code_str, msg = status_sent, ""
                code = int(code_str)
                self.send_response(code, msg)
                header_keys = set()
                for key, value in headers_sent:
                    self.send_header(key, value)
                    key = key.lower()
                    header_keys.add(key)
                if not (
                        "content-length" in header_keys
                        or self.command == "HEAD"
                        or code < 200
                        or code in (204, 304)
                ):
                    self.close_connection = True
                    self.send_header("Connection", "close")
                self.end_headers()

            self.wfile.write(data)
            self.wfile.flush()

        response = get_response(buffer, headers)

        def start_response(response: "Response", event_type: 'IntEnum'):
            nonlocal headers_set, status_set, request_sucess, body
            headers = []

            try:
                if event_type != EventStatus.DELETE_CHANNEL:
                    response.run()
            except Exception as e:
                if isinstance(e, KeyError):
                    status_code = http.HTTPStatus.BAD_REQUEST.value
                else:
                    status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR.value
                body['status'] = 'failure'
                request_sucess = False

            if request_sucess:
                body['status'] = 'success'
                status_code = http.HTTPStatus.OK.value


            body['event_type'] = event_type
            body = json.dumps(body).encode()
            headers.append(('Content-Type', "application/json; charset=utf-8"))
            headers.append(('Content-Length', str(len(body))))

            headers_set = headers
            status_set = str(status_code)
            return body

        def execute():
            body = start_response(response, event_type)
            if not headers_sent:
                write(b"")
            write(body)

        try:
            execute()
        except (ConnectionError, socket.timeout) as e:
            self.connection_dropped(e)

    def connection_dropped(
            self, error: BaseException = None
    ) -> None:
        """Called if the connection was closed by the client.  By default
        nothing happens.
        """

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

    def _connection_dropped(self):
        pass


class Response:

    encoding_error = 'replace'
    charset = 'utf-8'
    default_directory = '/tmp/watcher'

    def __init__(self, buffer: t.BinaryIO, headers: t.Dict[str,str]):
        self.buffer = buffer
        self.headers = headers

    @property
    def stream(self) -> t.BinaryIO:
        """
        File like object stream.
        """
        return get_stream(self.buffer, self.headers)

    def get_data(self, as_text: bool = False) -> t.Union[t.ByteString, t.Text]:
        """
        Method to get data from stream.
        :param as_text:
            Whether to get data in the string form
        """
        stream = self.stream
        rv = stream.read()
        if as_text:
            rv = rv.decode(self.charset, self.encoding_error)
        return rv

    def get_file_names(self, headers: t.Dict[str, str]) -> t.List[str]:

        """
        Method to get file names from headers
        :param headers:
            HTTP Headers
        """
        files = headers.get('File-Name', None)

        if not files:
            # bad request error
            raise KeyError('File-Name header must be contained')
        file_lst = files.split(",")
        return [os.path.basename(file) for file in file_lst]

    def get_file_positions(self, headers: t.Dict[str, str]) -> t.Optional[t.List[int]]:
        """
        Method to get file postion.

        :param headers:
            HTTP Headers
        """
        positions = headers.get('Files-Position', None)
        content_length = get_content_length(headers)
        if positions:
            pos_lst = positions.split(",")
            return [int(pos) for pos in pos_lst]

        return [content_length]

    def _as_list(self, *args):

        return list(args)

    def save(self, stream: t.BinaryIO, file_name: str, directory: t.Optional[str]=None):
        """
        Method to save bytes to file

        :param stream:
            File bytes to be saved
        :param directory:
            Target directory
        :param file_name:
            File name to be saved
        :return:
        """
        if not directory:
            directory = self.default_directory
        if not os.path.exists(directory):
            os.makedirs(directory)

        seq = self._as_list(directory, file_name)
        target = ''.join(seq) if directory.endswith('/') else '/'.join(seq)

        with open(target, 'wb') as f:
            f.write(stream)

    def run(self):

        stream = self.stream
        positions = self.get_file_positions(self.headers)
        file_names = self.get_file_names(self.headers)
        pre_pos = 0
        while positions and file_names:
            pos = positions.pop(0)
            file_name = file_names.pop(0)
            if pre_pos == 0 and pos:
                chunk_size = pos
            elif pre_pos != 0 and pos:
                chunk_size = pos - pre_pos
            else:
                chunk_size = -1

            try:
                rv = stream.read(chunk_size)
                try:
                    self.save(rv, file_name)
                except OSError as e:
                    raise e
            except Exception as e:
                raise e
            pre_pos = pos


class HttpRequest:

    # HTTP Header
    create_connect_headers = {
        "Project-Name": 'test_project',
        "Event-Type": '4' # CreateChannel Event type
    }

    delete_connect_headers = {
        "Project-Name": 'test_project',
        "Event-Type": '5' # ChannelDelete Event type
    }

    # HTTP Method
    connection_method = 'POST'
    dropped_method    = 'DELETE'

    def __init__(self, watcher_server_address, source_address):
        self.host, self.port = watcher_server_address
        self.conn = http.client.HTTPConnection(self.host, self.port)

        self._source_address = source_address

    @property
    def source_address(self):

        source_address = self._source_address
        if isinstance(source_address, (tuple, list)):
            host, port = source_address

            if isinstance(port, int):
                port = str(port)
            source_address = f"{host}:{port}"
        return source_address


    def update_header(self, event_type: IntEnum):
        if event_type == event_type.DELETE_CHANNEL:
            headers = self.delete_connect_headers.copy()
        else:
            headers = self.create_connect_headers.copy()

        headers['Client-Address'] = self.source_address

        return headers


    def request(self, method: str, event_type: 'IntEnum')  -> 'http.client.HTTPResponse':
        """

        :param method:
            HTTP Method: POST or DELETE.
        :param event_type:
            Event type to send watcher server.
                example)
                    DELETE_CHANNEL, CREATE_CHANNEL
        :return:
        """
        headers = self.update_header(event_type)
        if method not in METHODS:
            raise ValueError("method must be in %s and %s" % (METHODS[0], METHODS[1]))

        self.conn.request(method, self.url, headers=headers)
        return self.conn.getresponse()

    def create_connection(self):
        """
        Method to make the connection with watcher.

        """
        method = self.connection_method
        event_type = EventStatus.CREATE_CHANNEL

        try:
            r = self.request(method, event_type)

        except Exception as e:
            raise e

        buffer = getattr(r, 'fp')
        headers = getattr(r, 'headers')
        response = get_response(buffer, headers)

        try:
            response.run()
        except Exception as e:
            raise e

        print("Create Connection")

    def drop_connection(self):
        method = self.connection_method
        event_type = EventStatus.DELETE_CHANNEL

        try:
            r = self.request(method, event_type)

        except Exception as e:
            raise e

        print("Drop Connection")

    @property
    def url(self):

        host, port = self.conn.host, self.conn.port
        if scheme != 'http':
            raise ValueError("must be http scheme")

        url = f'{scheme}://{host}:{port}/'
        return url



class HiveServer:

    def __init__(self,
                 server_address,
                 handler=TestHandler,
                 requester=HttpRequest,
                 watcher_server_address=watcher_server_address):

        self.server = HTTPServer(server_address, handler)
        self.is_should_keep_running = threading.Event()
        self.requester = requester(watcher_server_address,
                                   source_address=server_address)

    def on_start(self):
        self.requester.create_connection()

    def on_stop(self):
        self.requester.drop_connection()

    def stop(self):
        self.on_stop()

    def start(self):
        self.on_start()

    def serve(self):

        self.start()
        try:
            self.server.serve_forever()
        except Exception as e:
            raise e

        finally:
            self.stop()

    def close(self):
        self.server.shutdown()

if __name__ == '__main__':
    sv = HiveServer(frost_server_address)
    sv.serve()
