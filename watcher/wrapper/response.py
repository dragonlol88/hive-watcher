import threading
import typing as t

from werkzeug.wrappers import Response


class WatcherConnector:

    def __init__(self,
                 response_cls: Response,
                 event: threading.Event):

        self.event = event
        self.response_cls = response_cls
        self._injection_complete = False


    def inject_data(self,
                    data: t.Union[t.Iterable[bytes], bytes, t.Iterable[str], str]):

        # Todo data에 따라 먼저 인코드 디코드 시키는 코드 추가하기
        try:
            self.response_cls(data)
            self._injection_complete = True

        except Exception as e:
            raise e
        if self._injection_complete:
            self.event.set()

    def __call__(
            self, environ: "WSGIEnvironment", start_response: "StartResponse"
    ) -> t.Iterable[bytes]:
        """Process this response as WSGI application.
        :param environ: the WSGI environment.
        :param start_response: the response callable provided by the WSGI
                               server.
        :return: an application iterator
        """

        app_iter, status, headers = self.get_wsgi_response(environ)
        start_response(status, headers)
        return app_iter
