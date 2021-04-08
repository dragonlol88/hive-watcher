from src.common import EventStatus


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


class TransportError(Exception):
    """
    TransportError
    """
    @property
    def status_code(self):
        return self.args[0]

    def address(self):
        return self.args[1]

    @property
    def error(self):
        return self.args[2]

    @property
    def info(self):
        return self.args[3]

class ConnectionError(TransportError):
    """
    Connection Error
    """


class ConnectionTimeout(ConnectionError):
    """
    Connection Timeout Error
    """

EVENT_ERROR = {
    EventStatus.FILE_DELETED : FileDeletedError,
    EventStatus.FILE_CREATED: FileCreatedError,
    EventStatus.FILE_MODIFIED: FileModifiedError,
    EventStatus.CREATE_CHANNEL: ChannelCreatedError,
    EventStatus.DELETE_CHANNEL: ChannelDeletedError
}