import asyncio
import typing as t

from watcher.buffer import RemoteEventSymbol
from watcher.buffer import LocalEventSymbol

if t.TYPE_CHECKING:
    from watcher.type import Loop
    from watcher.hivewatcher import Watch
    from watcher.buffer import EventSymbol
    from .handlers import FileHandlerTypes, ChannelHandlerTypes


class EventBase:
    default_max_worker = 4
    event_type: t.Union[t.Any]
    handler_class: t.Union[t.Any, 'FileHandlerTypes', 'ChannelHandlerTypes']

    def __init__(self,
                 watch: 'Watch',
                 symbol: 'EventSymbol',
                 loop: 'Loop',
                 handler_class: t.Optional[
                     t.Union['FileHandlerTypes', 'ChannelHandlerTypes']] = None,
                 **kwargs):

        self.loop = loop
        self.symbol = symbol
        self.watch = watch
        self._lock = self.watch.lock

        if handler_class:
            self.handler_class = handler_class
        self.handler = self.handler_class(self, **kwargs)  # type: ignore

    @property
    def target(self) -> str:
        pass

    async def handle_event(self) -> t.Any:
        # 1. parameter 준비
        # 2. is coroutine 인지 아닌지
        handle = self.handler.handle_event()
        if not asyncio.iscoroutine(handle):
            raise TypeError('handle_event method must be coroutine.')
        return await handle

    async def __call__(self) -> t.Any:
        async with self._lock:
            response = await self.handle_event()
        return response
