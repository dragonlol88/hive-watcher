import threading
import typing as t


class WatcherConnector:

    def __init__(self, response_cls):

        self.response_cls = response_cls
        self._injection_complete = threading.Event()


    def inject_data(self,
                    data: t.Union[t.Iterable[bytes], bytes, t.Iterable[str], str],
                    header: t.Dict[str, str] = None):

        # Todo data에 따라 먼저 인코드 디코드 시키는 코드 추가하기

        try:
            self.response = self.response_cls(data)
            if header:
                self.response.headers.update(header)
        except Exception as e:
            raise e

        self.notify_injection_complete()

    def wait_until_injection_complete(self):
        """

        :return:
        """
        self._injection_complete.wait()

    def notify_injection_complete(self):
        """

        :return:
        """
        self._injection_complete.set()

    def injection_clear(self):
        """

        :return:
        """
        self._injection_complete.clear()

    def __call__(
            self, environ: "WSGIEnvironment", start_response: "StartResponse"
    ) -> t.Iterable[bytes]:
        """Process this response as WSGI application.
        :param environ: the WSGI environment.
        :param start_response: the response callable provided by the WSGI
                               server.
        :return: an application iterator
        """

        self.wait_until_injection_complete()
        app_iter = self.response.__call__(environ, start_response)
        self.injection_clear()
        return app_iter
