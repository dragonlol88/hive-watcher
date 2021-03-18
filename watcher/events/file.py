from .base import EventBase
from watcher import EventStatus
import watcher.events.handlers as h


class FileModifiedEvent(EventBase):
    event_type = EventStatus.FILE_MODIFIED
    handler_class = h.FileModifiedHandler


class FileCreatedEvent(EventBase):
    event_type = EventStatus.FILE_CREATED
    handler_class = h.FileCreatedHandler


class FileDeletedEvent(EventBase):
    event_type = EventStatus.FILE_DELETED
    handler_class = h.FileDeletedHandler
