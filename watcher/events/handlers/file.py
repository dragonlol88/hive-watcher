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

        try:
            value = self.event_type.value
            if not isinstance(value, str):
                value = str(value)
            if self.event_type in (EventStatus.FILE_CREATED,
                                   EventStatus.FILE_MODIFIED,
                                   EventStatus.FILE_DELETED):
                content_type = 'application/octet-stream'
            else:
                raise ValueError

        except (AttributeError, ValueError) as e:
            # log
            raise e

        else:
            self.headers.update({
                "File-Name": file_name,
                "Event-Type": value,
                "Content-Type": content_type
                }
            )
        return self.headers


    def event_action(self, response):
        """

        :param response:
        :return:
        """
        return response

    async def handle(self):
        responses = []
        method = self.method
        try:
            async for url in self.channels:
                response = await self.session.request(
                                        method,
                                        url,
                                        headers=self.headers,
                                        data=self.data,
                                        body=self.body)
                responses.append(response)
        except Exception as e:
            raise e

        finally:

            await self.session.close()

        return responses


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