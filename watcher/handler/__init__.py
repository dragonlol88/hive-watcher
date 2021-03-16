import urllib3
import typing as t
from watcher import EventStatus


event_type = {
                '1': 'file_deleted',
                '2': 'file_created',
                '3': 'file_modified',
            }

class HandlerBase:
    method = 'POST'
    def __init__(self,
                 event,
                 keep_alive=None,
                 http_auth=None,
                 headers=None):

        self._event = event
        self._watch = event.watch
        self.event_type = event.event_type
        self.keep_alive = keep_alive

        if not hasattr(self, "headers"):
            self.headers = headers or {}

        if http_auth is not None:
            if isinstance(http_auth, (tuple, list)):
                http_auth = ":".join(http_auth)
            self.headers.update(urllib3.make_headers(basic_auth=http_auth))

        # header
        # content-type
        # event-type
        # file-name

        content_type = self.headers.get('Content-Type', None)
        if not content_type and self.event_type:
            if self.event_type in (EventStatus.FILE_CREATED,
                                   EventStatus.FILE_MODIFIED,
                                   EventStatus.FILE_DELETED):
                self.headers['content-type'] = 'application/octet-stream'

        event_type_value = self.event_type.value
        if not isinstance(event_type_value, str):
             event_type_value = str(self.event_type.value)
        self.headers['event-type'] = event_type[event_type_value]

    @property
    def loop(self):
        return self._event.loop

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


    def action_event(self):
        """

        :return:
        """
        pass

    async def handle_event(self) -> t.List[t.Any]:
        responses = []

        await self.create_session()
        try:
            async for channel in self.channels:
                response = await self.request(
                    method=self.method,
                    url=channel,
                    headers=self.headers,
                    data=self.data,
                    body=self.body)
                print(response, self.event_type)
                responses.append(response)
        except Exception as e:
            raise e

        finally:
            try:
                self.action_event()

            except Exception as e:
                raise e

            await self.session.close()

        return responses

    async def request(self,
                      method,
                      url,
                      *,
                      headers=None,
                      data=None,
                      body=None,
                      **kwargs):
        if self.keep_alive:
            keep_alive = 'timeout=%d, max=%d' % \
                         (self.keep_alive, self._limit)
            headers['keep-alive'] = keep_alive

        if data:
            kwargs.update({'data': data})
        if body:
            kwargs.update({'body': body})

        method = method.lower()
        if hasattr(self.session, method):
            method = getattr(self.session, method)

        try:
            async with method(url, **kwargs) as resp:
                response = await resp.text()
        except Exception as e:
            raise e

        return response


    @property
    def data(self):
        return b''

    @property
    def body(self):
        pass

    async def create_session(self):
        """
        Coroutine to make self.session attribute
        :return:
        """
        pass

    def file_open(self):
        raise NotImplementedError

    def file_close(self):
        raise NotImplementedError
