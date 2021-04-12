import asyncio
import typing as t

if t.TYPE_CHECKING:
    from ..type import Loop
    from .handlers import FileHandlerTypes, ChannelHandlerTypes


class EventBase:
    default_max_worker = 4
    event_type: t.Union[t.Any]
    handler_class: t.Union[t.Any, 'FileHandlerTypes', 'ChannelHandlerTypes']

    def __init__(self,
                 manager,
                 transporter,
                 symbol: 'EventSymbol',
                 loop: 'Loop',
                 handler_class: t.Optional[
                     t.Union['FileHandlerTypes', 'ChannelHandlerTypes']] = None,
                 **kwargs):

        self.loop = loop
        self.symbol = symbol
        self.transporter = transporter
        self.manager = manager
        self._lock = manager.lock
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

    async def run_event(self) -> t.Any:
        exception = None
        async with self._lock:
            try:
                response = await self.handle_event()
            except Exception as exc:
                # Process additional error to void deadlock
                exception = exc

        if exception:
            raise exception
        return response
