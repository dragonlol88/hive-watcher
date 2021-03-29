import io
import asyncio
import typing as t
import functools
import aiofiles
import concurrent.futures
from json import JSONEncoder
from json import JSONDecoder
from json import JSONDecodeError
from json import detect_encoding                                                # type: ignore
from werkzeug.wsgi import LimitedStream


READ_SIZE = 64 * 1024


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


def get_file_io(file_name: str, mode: t.Optional[str] = 'rb') -> AsyncFileIO:
    """
    Function to get async file object.

    :param file_name:
        File path.
    """
    _open = functools.partial(
        aiofiles.threadpool._open,  # type: ignore
        mode=mode
    )

    return AsyncFileIO(_open(file_name))


async def stream(file: str, mode: str = 'rb'):
    """
    Coroutine to generate file byte stream for massive file transfer.

    :param file:
        file name will be called
    :param mode:
        file mode

    """

    file_io = get_file_io(file, mode)
    buffer = await file_io.open()
    chunk = await buffer.read(READ_SIZE)
    while chunk:
        yield chunk
        chunk = await buffer.read(READ_SIZE)

    await file_io.close()


class AsyncJson:

    _default_encoder = JSONEncoder(
                            skipkeys=False,
                            ensure_ascii=True,
                            check_circular=True,
                            allow_nan=True,
                            indent=4,
                            separators=None,
                            default=None,
                            )

    _default_decoder = JSONDecoder(
                            object_hook=None,
                            object_pairs_hook=None)

    _default_executor = concurrent.futures.ThreadPoolExecutor

    def __init__(self,
                 target_path: t.Optional[str] = None,
                 executor: t.Optional[concurrent.futures.ThreadPoolExecutor] = None,
                 worker: t.Optional[int] = None):

        self.target_path = target_path
        self.executor = executor
        self.worker = worker

    @t.no_type_check
    async def dump(self,
                   obj: t.Dict[str, t.Any],
                   fp: t.Optional[t.Union[io.TextIOBase, io.BufferedIOBase]] = None,
                   *,
                   mode: t.Optional[str] = 'w',
                   **kw):
        """
        Coroutine to save data in json formation.

        :param obj:
            Data to be saved in json formation.
        :param fp:
            File object.
        :param mode:
            File mode. 'w', 'r', 'rb', 'wb'
        :param kw:
            Additional argument.
        """
        loop = asyncio.get_event_loop()
        iterable = self.make_iterencode(obj)

        def sync_write(iterable):
            for chunk in iterable:
                fp.write(chunk)

        async def async_write(iterable):
            for chunk in iterable:
                await fp.write(chunk)

        if fp is None:
            fp = get_file_io(self.target_path, mode)

        if not hasattr(fp, 'close'):
            raise AttributeError("fp must have close method")

        if asyncio.iscoroutine(fp):
            fp = await fp.open()
            await async_write(iterable)
            await fp.close()

        elif isinstance(fp,
                        (aiofiles.threadpool.AsyncBufferedIOBase,
                         aiofiles.threadpool.AsyncTextIOWrapper)):
            await async_write(iterable)

        else:
            await loop.run_in_executor(self.executor, sync_write, iterable)

    @t.no_type_check
    async def load(self,
                   fp: t.Optional[t.Union[io.TextIOBase, io.BufferedIOBase]] = None,
                   *,
                   mode='rb'):
        """
        Coroutine to load data to json formation.

        :param fp:
            File object.
        :param mode:
            File mode. 'w', 'r', 'rb', 'wb'
        """
        if fp is None:
            fp = get_file_io(self.target_path, mode)                                        # type: ignore

        if not hasattr(fp, 'close'):
            raise AttributeError("fp must have close method")

        if asyncio.iscoroutine(fp):
            fp = await fp.open()
            read = await fp.read()

        elif isinstance(fp,
                        (aiofiles.threadpool.AsyncBufferedIOBase,
                         aiofiles.threadpool.AsyncTextIOWrapper)):
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

        json_data = self._default_decoder.decode(read)
        return json_data

    def make_iterencode(self, obj):
        return self._default_encoder.iterencode(obj)