import watcher.events.handlers as h

from .base import EventBase
from watcher import EventStatus


class CreateChannelEvent(EventBase):
    event_type = EventStatus.CREATE_CHANNEL
    handler_class = h.ChannelCreateHandler


class DeleteChannelEvent(EventBase):
    event_type = EventStatus.FILE_DELETED
    handler_class = h.ChannelDeleteHandler