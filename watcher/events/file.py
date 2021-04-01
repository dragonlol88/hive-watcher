from .base import EventBase
from watcher.common import EventStatus
import watcher.events.handlers as h


class FileModifiedEvent(EventBase):
    event_type = EventStatus.FILE_MODIFIED
    handler_class = h.FileModifiedHandler

    @property
    def target(self):
        return self.symbol.path


class FileCreatedEvent(FileModifiedEvent):
    event_type = EventStatus.FILE_CREATED
    handler_class = h.FileCreatedHandler                                                      # type: ignore


class FileDeletedEvent(FileModifiedEvent):
    event_type = EventStatus.FILE_DELETED
    handler_class = h.FileDeletedHandler                                                      # type: ignore
