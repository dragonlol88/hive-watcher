# mypy: ignore-errors
import queue
import asyncio
import threading
import typing as t

from enum import IntEnum
from .wrapper.stream import get_file_io
from .wrapper.stream import AsyncJson

DEFAULT_QUEUE_TIMEOUT = 1
QUEUE_MAX_SIZE = 4200

try:
    from asyncio import get_running_loop
except ImportError:

    def get_running_loop():
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            raise RuntimeError("no running event loop")
        return loop

# asyncio types
Task = asyncio.Task
Future = asyncio.Future
AsyncEvent = asyncio.Event
Loop = asyncio.AbstractEventLoop

try:
    from asyncio.base_futures import _PENDING, _CANCELLED, _FINISHED
except:
    _PENDING  = 'PENDING'
    _CANCELLED = 'CANCELLED'
    _FINISHED  = 'FINISHED'


class EventSentinel(IntEnum):

    def __new__(cls, value, phrase):
        obj = int.__new__(cls, value)
        obj._value_ = value

        obj.phrase = phrase
        return obj

    FILE_DELETED = (1, 'File Deleted')
    FILE_CREATED = (2, 'File Created')
    FILE_MODIFIED = (3, 'File Modified')
    CREATE_CHANNEL = (4, 'Channel Created')
    DELETE_CHANNEL = (5, 'Channel Deleted')


class UniqueList(list):

    def append(self, item):
        if item not in self:
            super().append(item)

    def pop(self, item=None):
        idx = None
        if item is None:
            return super().pop()
        for i, c in enumerate(self):
            if item == c:
                idx = i
        if idx is None:
            raise KeyError
        return super().pop(idx)

    def __hash__(self):
        return id(self)


class EventQueue(queue.Queue):

    def __init__(self, maxsize=QUEUE_MAX_SIZE):
        super().__init__(maxsize)


class BaseThread(threading.Thread):
    """ Convenience class for creating stoppable threads. """

    def __init__(self):
        threading.Thread.__init__(self)
        if hasattr(self, 'daemon'):
            self.daemon = True
        else:
            self.setDaemon(True)
        self._stopped_event = threading.Event()

        if not hasattr(self._stopped_event, 'is_set'):
            self._stopped_event.is_set = self._stopped_event.isSet

    @property
    def stopped_event(self):
        return self._stopped_event

    def should_keep_running(self) -> bool:
        """Determines whether the thread should continue running."""
        return not self._stopped_event.is_set()

    def on_thread_stop(self):
        """Override this method instead of :meth:`stop()`.
        :meth:`stop()` calls this method.
        This method is called immediately after the thread is signaled to stop.
        """
        pass

    def stop(self) -> None:
        """Signals the thread to stop."""
        self._stopped_event.set()
        self.on_thread_stop()

    def on_thread_start(self) -> None:
        """Override this method instead of :meth:`start()`. :meth:`start()`
        calls this method.
        This method is called right before this thread is started and this
        object’s run() method is invoked.
        """
        pass

    def start(self) -> None:
        self.on_thread_start()
        threading.Thread.start(self)


class JsonIO:

    def __init__(self, path: str):
        self.path = path

    async def dump_to_json(self, data: t.Dict[str, t.Any]) -> None:
        """

        :param data:
        :return:
        """
        json = AsyncJson()
        async with get_file_io(self.path, 'w') as af:
            await json.dump(data, af)

    async def load_to_json(self) -> t.Dict[str, t.Dict[str, t.Any]]:
        """
        Load sample from json file.
        :return:
            Dictionary object. key is project.
        """
        json = AsyncJson()
        try:
            async with get_file_io(self.path, 'r') as af:
                data = await json.load(af)
        except FileNotFoundError:
            data = {}
        return data


class FileIO(JsonIO):

    def __init__(self, path: str, files: t.Dict[str, t.Any]):
        super().__init__(path)
        self.files = files

    async def write(self):
        await self.dump_to_json(self.files)

    async def read(self):
        data = await self.load_to_json()
        self.files.update(data)


class _EventBase(str):
    def __repr__(self):
        return self.__name__


def make_event(name):
    cls = _EventBase(name)
    cls.__class__ = type(cls)
    cls.__name__ = name
    return cls


DISCARD_CHANNEL = make_event("add_channel")
DISCARD_PATH = make_event("discard_path")
ADD_CHANNEL = make_event("add_channel")
ADD_PATH = make_event("add_path")
TRANSPORT_FILE = make_event("transport_file")
EOF = make_event('EOF')
