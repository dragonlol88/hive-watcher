import typing as t

from watcher.buffer import RemoteEventSymbol
from watcher.buffer import LocalEventSymbol


if t.TYPE_CHECKING:
    from watcher.type import Loop
    from watcher.watcher import Watch
    from watcher.buffer import EventSymbol
    from .handlers import FileHandlerTypes, ChannelHandlerTypes

class EventBase:

    default_max_worker = 4
    event_type: t.Union[t.Any]
    handler_class: t.Union[t.Any, FileHandlerTypes, ChannelHandlerTypes]

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

        if isinstance(symbol, LocalEventSymbol):
            self._target = symbol.path

        elif isinstance(symbol, RemoteEventSymbol):
            self._target = symbol.client_host

        if handler_class:
            self.handler_class = handler_class

        self.handler = self.handler_class(self, **kwargs)                                     # type: ignore

    @property
    def target(self) -> str:
        return self._target

    def evoke_failure_logs(self):
        pass

    def evoke_success_logs(self):
        pass


    async def handle_event(self) -> t.Any:
        # 1. parameter 준비
        # 2. is coroutine 인지 아닌지
        # 3. 성공 or 실패 check 어떻게 하지??
        handle = self.handler.handle_event

        # try:
        # if not is_coroutine:
        #     response = await self.run_in_executor(handle)
        # else:
        response = await handle()
        # except:
        #     response = await self._handle_failure()

        return response

    @t.no_type_check
    async def _handle_failure(self):
        return

    async def __call__(self) -> t.Any:
        async with self._lock:
            # try:
            response = await self.handle_event()
            # except:
            #     self.evoke_failure_logs()
            # self.evoke_success_logs()
        return response