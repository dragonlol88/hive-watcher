import time
import json
import socket
import threading
import http.server

server_address = ('127.0.0.1', 7777)

class TestHandler(http.server.BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

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

class TestServer(threading.Thread):

    def __init__(self, server_address, handler=TestHandler):
        super(TestServer, self).__init__()
        self.server = http.server.HTTPServer(server_address, handler)
        self.start()

    def on_thread_start(self):
        pass

    def on_thread_stop(self):
        pass

    def start(self):
        self.on_thread_start()
        super(TestServer, self).start()

    def run(self):
        self.server.serve_forever()

def server_on():
    server = TestServer(server_address)
    url = 'http://127.0.0.1:7777'
    f = open("/Users/sunny/sunny-project/hive/test-config/project2/synonym/test12.txt", 'rb')
    # response = requests.post(url, data=f.read(), headers={"event-type": "file_created", "file-name": 'test12.txt'})

    while True:
        try:
            # print(response.json())
            time.sleep(3)
        except KeyboardInterrupt:
            server.join()
            break

if __name__ == '__main__':
    server_on()