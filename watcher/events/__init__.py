import typing as t
from watcher.common import EventStatus

from .base import EventBase
from .file import (FileModifiedEvent,
                   FileCreatedEvent,
                   FileDeletedEvent)

from .connection import CreateChannelEvent, DeleteChannelEvent

FileEventTypes = t.Union[FileModifiedEvent, FileCreatedEvent, FileDeletedEvent]
ChannelEventTypes = t.Union[CreateChannelEvent, DeleteChannelEvent]

__all__ = ("EventBase",
           "FileModifiedEvent",
           "FileCreatedEvent",
           "FileDeletedEvent",
           "CreateChannelEvent",
           "DeleteChannelEvent")

HIVE_EVENTS = {
    EventStatus.FILE_DELETED: FileDeletedEvent,
    EventStatus.FILE_CREATED: FileCreatedEvent,
    EventStatus.FILE_MODIFIED: FileModifiedEvent,
    EventStatus.CREATE_CHANNEL: CreateChannelEvent,
    EventStatus.DELETE_CHANNEL: DeleteChannelEvent
}