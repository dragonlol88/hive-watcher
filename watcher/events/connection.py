import typing as t

import watcher.events.handlers as h

from .base import EventBase
from watcher.common import EventStatus

class ChannelEvent(EventBase):

    def __init__(self,
                 watch,
                 symbol,
                 loop=None,
                 handler_class=None,
                 **kwargs):
        self.connector = symbol.connector
        super().__init__(watch, symbol, loop, handler_class, **kwargs)

    @property
    def target(self):
        return self.symbol.client_address


class CreateChannelEvent(ChannelEvent):
    event_type = EventStatus.CREATE_CHANNEL
    handler_class = h.ChannelCreateHandler


class DeleteChannelEvent(ChannelEvent):
    event_type = EventStatus.DELETE_CHANNEL
    handler_class = h.ChannelDeleteHandler