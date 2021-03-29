import io
import asyncio
import typing as t
import functools
import aiofiles

from json import JSONEncoder
from json import JSONDecoder
from json import JSONDecodeError
from json import detect_encoding                                                # type: ignore
from werkzeug.wsgi import LimitedStream



class AsyncFileIO(aiofiles.base.AiofilesContextManager):

    def __init__(self, coro) -> object:
        super(AsyncFileIO, self).__init__(coro)

    @t.no_type_check
    async def open(self):
        self._obj = await self._coro
        return self._obj

    @t.no_type_check
    async def close(self):
        await self._obj.close()
        self._obj = None


def get_file_io(file_name: str, mode: t.Optional[str] = 'rb') -> AsyncFileIO:
    """

    :param file_name:
    :return:
    """
    _open = functools.partial(
        aiofiles.threadpool._open,  # type: ignore
        mode=mode
    )

    return AsyncFileIO(_open(file_name))


class AsyncJson:

    _default_encoder = JSONEncoder(
                            skipkeys=False,
                            ensure_ascii=True,
                            check_circular=True,
                            allow_nan=True,
                            indent=None,
                            separators=None,
                            default=None,
                            )

    _default_decoder = JSONDecoder(
                            object_hook=None,
                            object_pairs_hook=None)

    def __init__(self, target_path: str, executor=None, worker=None):

        self.target_path = target_path
        self.executor = executor

    async def dump(self,
                   obj: t.Dict[str, t.Any],
                   fp: t.Optional[t.Union[io.TextIOBase, io.BufferedIOBase]] = None,
                   *,
                   mode: t.Optional[str] = 'w',
                   **kw):

        loop = asyncio.get_event_loop()
        iterable = self.make_iterencode(obj)

        def sync_write():
            for chunk in iterable:
                fp.write(chunk)

        if fp is None:
            fp = get_file_io(self.target_path, mode)

        if not hasattr(fp, 'close'):
            raise AttributeError("fp must have close method")

        if asyncio.iscoroutine(fp):
            fp = await fp.open()                                                           # type: ignore
            for chunk in iterable:
                await fp.write(chunk)
            await fp.close()

        else:
            await loop.run_in_executor(self.executor, sync_write)
            fp.close()

    async def load(self,
                   fp: t.Optional[t.Union[io.TextIOBase, io.BufferedIOBase]] = None,
                   *,
                   mode='rb'):

        loop = asyncio.get_event_loop()
        if fp is None:
            fp = get_file_io(self.target_path, mode)

        if not hasattr(fp, 'close'):
            raise AttributeError("fp must have close method")

        if asyncio.iscoroutine(fp):
            fp = await fp.open()
            read = await fp.read()
        else:
            read = fp.read()

        if isinstance(read, str):
            if read.startswith('\ufeff'):
                raise JSONDecodeError("Unexpected UTF-8 BOM (decode using utf-8-sig)",
                                      read, 0)
        else:
            if not isinstance(read, (bytes, bytearray)):
                raise TypeError(f'the JSON object must be str, bytes or bytearray, '
                                f'not {read.__class__.__name__}')
            read = read.decode(detect_encoding(read), 'surrogatepass')

        return self._default_decoder.decode(read)

    def make_iterencode(self, obj):
        return self._default_encoder.iterencode(obj)