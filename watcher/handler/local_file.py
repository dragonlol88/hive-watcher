import os
import typing as t
import functools
import aiohttp
import aiofiles
from . import HandlerBase
from ..utils import get_running_loop

_open = functools.partial(
            aiofiles.threadpool._open,
            mode='rb'
        )

READ_SIZE = 64 * 1024
EVENT_SLEEP_TIME = 1e-5

class AsyncFileIO(aiofiles.base.AiofilesContextManager):

    def __init__(self, coro):
        super(AsyncFileIO, self).__init__(coro)

    async def open(self):
        self._obj = await self._coro
        return self._obj

    async def close(self):
        await self._obj.close()
        self._obj = None

class FileModifiedHandler(HandlerBase):
    method = 'POST'
    def __init__(self,
                 event,
                 http_auth=None,
                 keep_alive=15,
                 timeout=300,
                 maxsize=100,
                 headers=None,
                 **kwargs):

        super().__init__(event, keep_alive, http_auth, headers)

        self._limit = maxsize

        self.timeout = timeout
        self.session = None
        self.aiofile = None

        self._file = self._event.target

        file_name = self.headers.get('file-name', None)
        if not file_name:
            file_name = os.path.basename(self._file)
            # remote client 파일 저장 장소는 client에서 설정 할 수 있도록하기
            self.headers['file-name'] = file_name

    @property
    def data(self):
        """

        :return:
        """
        stream = self._stream

        return stream(self._file)

    async def _create_aiohttp_session(self):

        if not self.loop:
            loop = get_running_loop()

        self.session = aiohttp.ClientSession(
            loop=loop,
            auto_decompress=True,
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(
                            total=self.timeout),
            connector=aiohttp.TCPConnector(
                            limit=self._limit,
                            use_dns_cache=True
            )
        )

    async def create_session(self):
        """

        :return:
        """
        if self.session is None:
            await self._create_aiohttp_session()

    async def _stream(self, file):
        """
        Method to generate file byte stream for massive file transfer.

        :param file_name:
            file name will be called

        """
        await self._set_aiofile(file)

        file = await self.file_open()
        chunk = await file.read(READ_SIZE)
        chunk += chunk
        while chunk:
            yield chunk
            chunk = await file.read(READ_SIZE)
        await self.file_close()

    async def _set_aiofile(self, file_name):
        """

        :param
            file_name:
        """
        self.aiofile = AsyncFileIO(
            _open(file_name)
        )

    async def file_open(self):
        """
        Method to open python file object

        """
        return await self.aiofile.open()

    async def file_close(self):
        """
        Method to close python file object
        """
        await self.aiofile.close()


class FileCreatedHandler(FileModifiedHandler):

    method = 'POST'

    def action_event(self):
        self.watch.add_path(self._file)


class FileDeletedHandler(FileModifiedHandler):
    method = "POST"

    @property
    def data(self):
        return b''

    def action_event(self):
        self.watch.discard_path(self._event.target)

