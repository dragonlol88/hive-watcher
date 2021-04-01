import os
import typing as t

from . import HandlerBase
from . import Session

from watcher.common import EventStatus
from watcher.wrapper.stream import stream

EVENT_SLEEP_TIME = 1e-5

if t.TYPE_CHECKING:
    from ..file import FileDeletedEvent
    from ..file import FileCreatedEvent
    from ..file import FileModifiedEvent


class FileHandler(HandlerBase):
    method = 'POST'

    def __init__(self,
                 event: t.Union['FileDeletedEvent',
                                'FileCreatedEvent',
                                'FileModifiedEvent'],
                 **kwargs):

        super().__init__(event)

        self.file = self.event.target
        self.headers = self.update_headers(self.file)
        self.session = Session(loop=self.loop, headers=self.headers, **kwargs)

    @property
    def data(self):
        """

        :return:
        """
        return stream(self.file)

    @property
    def body(self) -> bytes:
        """

        :return:
        """
        return b''

    def update_headers(self, file):
        """

        :return:
        """

        self.headers: t.Dict[str, str] = {}
        file_name = os.path.basename(file)
        event_type_num = self.event_type.value

        if not isinstance(event_type_num, str):
            event_type_num = str(event_type_num)
        if self.event_type in (EventStatus.FILE_CREATED,
                               EventStatus.FILE_MODIFIED,
                               EventStatus.FILE_DELETED):
            content_type = 'application/octet-stream'
        else:
            raise ValueError("%s not supported event" % (repr(self.event_type)))

        self.headers.update({
            "File-Name": file_name,
            "Event-Type": event_type_num,
            "Content-Type": content_type
        }
        )
        return self.headers

    async def handle(self):

        responses = []
        method = self.method

        async for url in self.channels:
            response = await self.session.request(
                method,
                url,
                headers=self.headers,
                data=self.data,
                body=self.body)
            responses.append(response)
        await self.session.close()
        return responses

    def event_action(self, response):
        """

        :param response:
        :return:
        """
        return response


class FileCreatedHandler(FileHandler):
    method = 'POST'

    def event_action(self, response: t.Any) -> t.Any:
        self.watch.add_path(self.file)
        return response


class FileDeletedHandler(FileHandler):
    method = "POST"

    @property
    def data(self) -> bytes:
        return b''

    def event_action(self, response):
        self.watch.discard_path(self.event.target)
        return response


class FileModifiedHandler(FileHandler):
    method = 'POST'
