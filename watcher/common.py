import os
import queue
import threading

import asyncio
import typing as t
from enum import IntEnum
from .wrapper.stream import get_file_io
from .wrapper.stream import AsyncJson

DEFAULT_QUEUE_TIMEOUT = 1
QUEUE_MAX_SIZE = 4200
WATCH_STORE_KEY = ['paths', 'channels']


class EventStatus(IntEnum):

    def __new__(cls, value, phrase):
        obj = int.__new__(cls, value)
        obj._value_ = value

        obj.phrase = phrase
        return obj

    FILE_DELETED   = (1, 'File Deleted')
    FILE_CREATED   = (2, 'File Created')
    FILE_MODIFIED  = (3, 'File Modified')
    CREATE_CHANNEL = (4, 'Channel Created')
    DELETE_CHANNEL = (5, 'Channel Deleted')


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


class WatchIO:

    def __init__(self, watch_path: str, watches: t.Dict[str, t.Any]):

        self.watches = watches
        self.watch_path = watch_path

    async def record(self):
        """
        Record watch information in json formation.
        """

        watches = self.watches
        watch_dic = {}

        for key, watch in watches.items():
            watch_dic[key] = {}
            async with watch.lock:
                for store_key in WATCH_STORE_KEY:
                    value = getattr(watch, store_key)
                    if isinstance(value, set):
                        value = list(value)
                    watch_dic[key][store_key] = value
                await asyncio.sleep(0.1)

        await self.dump_to_json(watch_dic)

    @t.no_type_check
    async def load(self, watch_cls, loop) -> None:
        """
        Transfer data from json file to Watch object.
        :param watch_cls:
                watch class
        :param loop:
                Event loop
        """
        json_data = await self.load_to_json()
        for key, data in json_data.items():
            watch = watch_cls(key, loop)
            for store_key in WATCH_STORE_KEY:
                value = set(data[store_key])
                setattr(watch, store_key, value)
            self.watches[key] = watch

    async def dump_to_json(self, data: t.Dict[str, t.Dict[str, t.Iterable]]) -> None:
        """

        :param data:
        :return:
        """
        json = AsyncJson()
        async with get_file_io(self.watch_path, 'w') as af:
            await json.dump(data, af)

    async def load_to_json(self) -> t.Dict[str, t.Dict[str, t.Iterable]]:
        """
        Load data from json file.
        :return:
            Dictionary object. key is project.
        """
        json = AsyncJson()
        async with get_file_io(self.watch_path, 'r') as af:
            data = await json.load(af)
        return data














