import typing as t
from .base import HandlerBase
from .client import Session
from .file import FileCreatedHandler, FileModifiedHandler, FileDeletedHandler
from .connection import ChannelDeleteHandler, ChannelCreateHandler

FileHandlerTypes = t.Union[FileModifiedHandler, FileCreatedHandler, FileDeletedHandler]
ChannelHandlerTypes = t.Union[ChannelCreateHandler, ChannelDeleteHandler]

__all__ = ("HandlerBase",
           "FileCreatedHandler",
           "FileDeletedHandler",
           "FileModifiedHandler",
           "ChannelDeleteHandler",
           "ChannelCreateHandler",
           "Session")