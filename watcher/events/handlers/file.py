import os
import typing as t
import functools
import aiofiles

from . import HandlerBase
from . import Session

from watcher import EventStatus
from watcher.type import Loop

_open = functools.partial(
            aiofiles.threadpool._open,                                                                    # type: ignore
            mode='rb'
        )

READ_SIZE = 64 * 1024
EVENT_SLEEP_TIME = 1e-5


class AsyncFileIO(aiofiles.base.AiofilesContextManager):

    def __init__(self, coro):
        super(AsyncFileIO, self).__init__(coro)

    @t.no_type_check
    async def open(self):
        self._obj = await self._coro
        return self._obj

    @t.no_type_check
    async def close(self):
        await self._obj.close()
        self._obj = None


def get_file_io(file_name: str) -> AsyncFileIO:
    """

    :param file_name:
    :return:
    """

    return AsyncFileIO(_open(file_name))


async def stream(file: str):
    """
    Coroutine to generate file byte stream for massive file transfer.

    :param file:
        file name will be called

    """

    fileio = get_file_io(file)
    buffer = await fileio.open()
    chunk = await buffer.read(READ_SIZE)
    chunk += chunk

    while chunk:
        yield chunk
        chunk = await buffer.read(READ_SIZE)

    await fileio.close()




class FileHandler(HandlerBase):

    method = 'POST'

    def __init__(self,
                 event: 'Event',                                                                          # type: ignore
                 headers: t.Dict[str, str] = {},
                 **kwargs):

        super().__init__(event)

        self.watch = event.watch
        self.headers = headers
        self._file = self.event.target

        file_name = self.headers.get('file-name', None)
        if not file_name:
            file_name = os.path.basename(self._file)
            # remote client 파일 저장 장소는 client에서 설정 할 수 있도록하기
            self.headers['file-name'] = file_name                                                          #type: ignore

        event_type_value = self.event_type.value
        if not isinstance(event_type_value, str):
             event_type_value = str(self.event_type.value)
        self.headers['event-type'] = event_type_value

        content_type = self.headers.get('Content-Type', None)
        if not content_type and self.event_type:
            if self.event_type in (EventStatus.FILE_CREATED,
                                   EventStatus.FILE_MODIFIED,
                                   EventStatus.FILE_DELETED):
                self.headers['Content-Type'] = 'application/octet-stream'

        self.session = Session(loop=self.loop, headers=self.headers, **kwargs)

    @property
    def loop(self) -> Loop:
        """

        :return:
        """
        return self.event.loop

    @property
    async def channels(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for channel in self.watch.channels:
            yield channel

    @property
    async def paths(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for path in self.watch.paths:
            yield path

    @property
    def data(self) -> t.Any:
        """

        :return:
        """

        return stream(self._file)

    @property
    def body(self) -> bytes:
        """

        :return:
        """
        return b''

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
        self.watch.add_path(self._file)
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