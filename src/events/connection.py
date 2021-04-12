import src.events.handlers as h

from .base import EventBase
from ..common import EventSentinel


class ChannelEvent(EventBase):

    def __init__(self,
                 manager,
                 transporter,
                 symbol,
                 loop=None,
                 handler_class=None,
                 **kwargs):
        self.connector = symbol.connector
        super().__init__(manager, transporter, symbol, loop, handler_class, **kwargs)

    @property
    def target(self):
        return self.symbol.client_address


class CreateChannelEvent(ChannelEvent):
    event_type = EventSentinel.CREATE_CHANNEL
    handler_class = h.ChannelCreateHandler


class DeleteChannelEvent(ChannelEvent):
    event_type = EventSentinel.DELETE_CHANNEL
    handler_class = h.ChannelDeleteHandler