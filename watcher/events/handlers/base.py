import logging
import typing as t

from watcher.common import EventStatus
from watcher.type import Loop

if t.TYPE_CHECKING:
    from watcher.events import ChannelEventTypes, FileEventTypes
    from watcher.type import Loop

logger = logging.Logger("hive-watcher")


class HandlerBase:

    # Http Rquest method
    method = 'POST'

    def __init__(self, event: t.Union['ChannelEventTypes', 'FileEventTypes']):

        self.event = event
        self.event_type = event.event_type
        self.watch = event.watch

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """
        return response

    async def handle(self):
        raise NotImplementedError

    async def handle_event(self) -> t.Any:

        try:
            response = await self.handle()

        except Exception as e:
            raise e

        response = self.event_action(response)

        return response

    @property
    def loop(self) -> Loop:
        """

        :return:
        """
        return self.event.loop

    @property
    async def channels(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for channel in self.watch.channels:
            yield channel

    @property
    async def paths(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for path in self.watch.paths:
            yield path

    def log_fails(self, file_name: str, event_type, channel: str):
        """file 이름  event type , channel 실패"""
        pass


    def log_success(self):
        pass

    event_response = {member.value: member.phrase                                              #type: ignore
                      for member in EventStatus.__members__.values()}