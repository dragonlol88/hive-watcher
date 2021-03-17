from watcher import EventStatus

from .file import (FileModifiedEvent,
                   FileCreatedEvent,
                   FileDeletedEvent)

from .connection import CreateChannelEevent, DeleteChannelEevent

__all__ = (FileModifiedEvent,
           FileCreatedEvent,
           FileDeletedEvent,
           CreateChannelEevent,
           DeleteChannelEevent)

HIVE_EVENTS = {
    EventStatus.FILE_DELETED: FileDeletedEvent,
    EventStatus.FILE_CREATED: FileCreatedEvent,
    EventStatus.FILE_MODIFIED: FileModifiedEvent,

}