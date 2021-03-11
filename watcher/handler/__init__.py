import urllib3

class HandlerBase:

    def __init__(self,
                 event,
                 http_auth=None,
                 headers=None):

        self._event = event
        self._watch = event.watch
        if not hasattr(self, "headers"):
            self.headers = headers or {}

        if http_auth is not None:
            if isinstance(http_auth, (tuple, list)):
                http_auth = ":".join(http_auth)
            self.headers.update(urllib3.make_headers(basic_auth=http_auth))

    @property
    def loop(self):
        return self._event.loop

    # @loop.setter
    # def loop(self, loop):
    #     self.loop = loop

    @property
    def watch(self):
        return self._watch

    @property
    async def channels(self):
        for channel in self.watch._channels:
            yield channel

    @property
    async def paths(self):
        for path in self.watch._paths:
            yield path


    async def handle(self):
        pass