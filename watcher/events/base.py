import typing as t
import concurrent.futures

class EventBase:

    default_max_worker = 4

    def __init__(self,
                 watch: "Watch",
                 symbol: "Symbol",
                 loop=None,
                 executor=None,
                 handler_class=None,
                 **kwargs):

        self.loop = loop
        self._watch = watch
        self._executor = executor
        self._lock = self._watch.lock

        self._target = None # target file path
        if hasattr(symbol, 'path'):
            self._target = symbol.path

        if handler_class:
            self.handler_class = handler_class

        self.handler = self.handler_class(self, **kwargs)

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
        handle_event = self.handler.handle_event

        # try:
        # if not is_coroutine:
        #     response = await self.run_in_executor(handle)
        # else:
        response = await handle_event()
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