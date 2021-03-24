import json
import socket
import threading
import http.server

from watcher import EventStatus

frost_server_address = ('127.0.0.1', 7777)
blaze_server_address = ('127.0.0.1', 7777)


class TestHandler(http.server.BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def get_data(self):
        cl = self.headers['Content-Length']
        data = self.rfile.read(int(cl))
        return data

    def run_event(self):

        self.send_response(http.server.HTTPStatus.OK)
        body = 'hello world'
        length = self.headers['Content-Length']

        #content length 와 맞아야됨
        data = self.rfile.read(int(length))
        file_name = self.headers['File-Name']
        event_type = self.headers['Event-Type']

        if event_type and event_type == 'file_deleted':
            body = 'file_deleted'

        elif event_type and event_type != 'file_deleted':

            with open("./{}".format(file_name), 'wb') as f:
                f.write(data)

            if event_type == 'file_created':
                body = 'file_created'

            elif event_type == 'file_modified':
                body = 'file_modified'

        resp = {
            "status": "success",
            "event-type": body
            }

        resp = json.dumps(resp).encode()

        self.send_header('Content-Type', "application/json; charset=utf-8")
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()



        self.wfile.flush()
        self.wfile.write(resp)

    def handle_one_request(self) -> None:

        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if self.parse_request():
                print(self.headers)
                self.run_event()
        except (ConnectionError, socket.timeout) as e:
            self._connection_dropped(e)

        except Exception as e:
            self.log_error("error: %s, ", e.__class__.__name__, e.args[0])

    def _connection_dropped(self):
        pass


class HiveServer(threading.Thread):

    def __init__(self, server_address, handler=TestHandler):
        super(HiveServer, self).__init__()
        self.server = http.server.HTTPServer(server_address, handler)
        self.start()

    def on_thread_start(self):
        pass

    def on_thread_stop(self):
        pass

    def start(self):
        self.on_thread_start()
        super(HiveServer, self).start()

    def run(self):
        self.server.serve_forever()