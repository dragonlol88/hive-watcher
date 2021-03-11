import os
import functools
import asyncio
import aiohttp
import aiofiles.base
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

    def __init__(self,
                 event,
                 http_auth=None,
                 keep_alive=15,
                 timeout=300,
                 maxsize=100,
                 headers=None):

        super().__init__(event, http_auth, headers)

        self._limit = maxsize
        self.keep_alive = keep_alive
        self.timeout = timeout
        self.session = None
        self.aiofile = None

    async def handle(self):

        stream = self._stream

        if self.session is None:
            await self._create_aiohttp_session()
        file_name = os.path.basename(self._event.target)
        async for host in self.channels:
            # try:
            async with self.session.post(
                    host, data=stream(self._event.target)) as resp:
                response = await resp.text()
                # print(response)
            # except:
            #     pass
        print(response)
        await self.session.close()
        await asyncio.sleep(3)
        print("modified")
        return response

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

    async def _stream(self, file_name):

        await self._set_aiofile(file_name)

        file = await self.file_open()
        chunk = await file.read(READ_SIZE)
        chunk = b'hello\r\n'+chunk
        while chunk:
            yield chunk
            chunk = await file.read(READ_SIZE)
        await self.file_close()

    async def _set_aiofile(self, file_name):
        self.aiofile =  AsyncFileIO(
            _open(file_name)
        )

    async def file_open(self):
        return await self.aiofile.open()

    async def file_close(self):
        await self.aiofile.close()


class FileCreatedHandler(FileModifiedHandler):

    def __init__(self,
                 event,
                 http_auth=None,
                 keep_alive=15,
                 timeout=300,
                 maxsize=100,
                 headers=None):

        super().__init__(event,
                         http_auth,
                         keep_alive,
                         timeout,
                         maxsize,
                         headers)

    async def handle(self):

        self._watch.add_path(self._event.target)

        stream = self._stream

        if self.session is None:
            await self._create_aiohttp_session()
        reponses = []
        file_name = os.path.basename(self._event.target)
        async for host in self.channels:
            # try:
            async with self.session.post(
                        host, data=stream(self._event.target)) as resp:
                response = await resp.text()
                reponses.append(response)
                # print(response)
            # except:
            #     pass
        print(response)
        await self.session.close()
        await asyncio.sleep(3)
        print("created")
        return response


class FileDeletedHandler(HandlerBase):

    def __init__(self,
                 event,
                 http_auth=None,
                 headers=None):
        super().__init__(event, http_auth, headers)


    async def handle(self):
        self.watch.discard_path(self._event.target)
        await asyncio.sleep(0)

