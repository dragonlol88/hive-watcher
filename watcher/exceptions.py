from .common import EventStatus
from aiohttp.client_exceptions import ClientConnectionError
from aiohttp.client_exceptions import ClientResponseError


class FilePaserError(Exception):
    """
    File parser Error
    """


class FileCreatedError(Exception):
    """
    File created error
    """


class FileModifiedError(Exception):
    """
    File modified error
    """


class FileDeletedError(Exception):
    """
    File deleted error
    """


class ChannelCreatedError(Exception):
    """
    Channel created error
    """


class ChannelDeletedError(Exception):
    """
    Channel created error
    """


class EventError(Exception):
    """
    Event error
    """


EVENT_ERROR = {
    EventStatus.FILE_DELETED : FileDeletedError,
    EventStatus.FILE_CREATED: FileCreatedError,
    EventStatus.FILE_MODIFIED: FileModifiedError,
    EventStatus.CREATE_CHANNEL: ChannelCreatedError,
    EventStatus.DELETE_CHANNEL: ChannelDeletedError
}