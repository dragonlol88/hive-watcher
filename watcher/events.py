import typing as t
import asyncio
import concurrent.futures
import watcher.handler.remote_file as rf
import watcher.handler.local_file as lf

from enum import IntEnum

class EventStatus(IntEnum):
    FILE_DELETED   = 1
    FILE_CREATED   = 2
    FILE_MODIFIED  = 3
    CREATE_CHANNEL = 4
    DELETE_CHANNEL = 5


class EventBase:

    default_max_worker = 4

    def __init__(self,
                 watch: "Watch",
                 target: str,
                 loop=None,
                 executor=None,
                 handler_class=None):

        # if loop is None:
        #     loop = asyncio.get_running_loop()

        self.loop = loop
        self._watch = watch
        self._lock = self._watch.lock
        self._target = target
        self._executor = executor
        self.handler = self.handler_class(self)

    @property
    def watch(self):
        return self._watch

    @property
    def target(self):
        return self._target

    def evoke_failure_logs(self):
        pass

    def evoke_success_logs(self):
        pass

    def _set_executor(self, max_worker=None):

        if not max_worker:
            max_worker = self.default_max_worker
        self._executor = \
            concurrent.futures.ThreadPoolExecutor(max_worker=max_worker)

    async def run_in_executor(self,
                              func: t.Callable,
                              *args: t.Any):

        #no async http 일 때
        loop = self.loop
        if not self._executor:
            self._set_executor()
        return await loop.run_in_executor(self._executor,
                                          func,
                                          *args)

    async def handle_event(self):
        # 1. parameter 준비
        # 2. is coroutine 인지 아닌지
        # 3. 성공 or 실패 check 어떻게 하지??
        handle = self.handler.handle
        is_coroutine = asyncio.iscoroutinefunction(handle)

        # try:
        # if not is_coroutine:
        #     response = await self.run_in_executor(handle)
        # else:
        response = await handle()
        # except:
        #     response = await self._handle_failure()

        return response

    async def _handle_failure(self):
        return

    async def __call__(self):
        async with self._lock:
            # try:
            response = await self.handle_event()
            # except:
            #     self.evoke_failure_logs()
            # self.evoke_success_logs()
        return response


class FileModifiedEvent(EventBase):
    event_type = EventStatus.FILE_MODIFIED
    handler_class = rf.FileModifiedHandler


class FileCreatedEvent(FileModifiedEvent):
    event_type = EventStatus.FILE_CREATED
    handler_class = rf.FileCreatedHandler


class FileDeletedEvent(EventBase):
    event_type = EventStatus.FILE_DELETED
    handler_class = rf.FileDeletedHandler


class CreateChannelEevent(EventBase):
    event_type = EventStatus.CREATE_CHANNEL
    handler_class = lf.ChannelCreateHandler


class DeleteChannelEevent(EventBase):
    event_type = EventStatus.FILE_DELETED
    handler_class = lf.ChannelDeleteHandler




HIVE_EVENTS = {
    EventStatus.FILE_DELETED: FileDeletedEvent,
    EventStatus.FILE_CREATED: FileCreatedEvent,
    EventStatus.FILE_MODIFIED: FileModifiedEvent,

}