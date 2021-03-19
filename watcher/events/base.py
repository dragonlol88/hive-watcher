import asyncio
import typing as t
import concurrent.futures


from watcher.buffer import RemoteEventSymbol
from watcher.buffer import LocalEventSymbol
from watcher.buffer import EventSymbol
from watcher.type import Loop

class EventBase:

    default_max_worker = 4
    event_type: t.Union[t.Any]

    def __init__(self,
                 watch: 'Watch',                                                             # type: ignore
                 symbol: EventSymbol,
                 loop: t.Optional[Loop] = None,
                 handler_class: t.Optional['Handler'] = None,                                #type: ignore
                 **kwargs):

        self.loop = loop
        self.symbol = symbol
        self.watch = watch

        self._lock = self.watch.lock
        self._target = None  # target file path

        if isinstance(symbol, LocalEventSymbol):
            self._target = symbol.path

        elif isinstance(symbol, RemoteEventSymbol):
            self._target = symbol.client_host

        if handler_class:
            self.handler_class = handler_class

        self.handler = self.handler_class(self, **kwargs)                                     # type: ignore

    @property
    def target(self) -> t.Optional[str]:
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