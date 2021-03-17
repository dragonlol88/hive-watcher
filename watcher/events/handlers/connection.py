import asyncio
from . import HandlerBase


class ChannelCreateHandler(HandlerBase):

    def __init__(self,
                 event,
                 http_auth=None,
                 headers=None):
        super().__init__(event, http_auth, headers)

    async def handle(self):
        async for channel in self.channels:
            self.watch.add_channel(channel)
            await asyncio.sleep(0)


class ChannelDeleteHandler(HandlerBase):

    def __init__(self,
                 event,
                 http_auth=None,
                 headers=None):
        super().__init__(event, http_auth, headers)

    async def handle(self):
        async for channel in self.channels:
            self.watch.discard_channel(channel)
            await asyncio.sleep(0)