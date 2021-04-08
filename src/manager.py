import copy
import asyncio
import typing as t

from collections import defaultdict
from .common import UniqueList
from .type import Loop


class _Manager(object):

    max_fail_num = 3

    def __init__(self, proj, loop):

        self.project = proj
        self.paths = UniqueList()
        self.channels = UniqueList()  # {"http://127.0.0.1:6666/", "http://192.168.0.230:5112/
        self.dead_count = defaultdict(int)
        self.connections = []

        self._loop = loop
        self._lock = asyncio.Lock(loop=self._loop)

    @property
    def lock(self):
        """
        Threading lock object.
        """
        return self._lock

    def mark_live(self, channel):
        try:
            del self.dead_count[channel]
        except KeyError:
            pass

    def mark_dead(self, channel):

        dead_count = self.dead_count[channel]
        if dead_count >= self.max_fail_num:
            self.discard_channel(channel)
        self.dead_count[channel] = dead_count + 1

    def set_connection(self, connection_class):
        raise NotImplementedError

    def get_connections(self):
        return self.connections

    def clear_connection(self):
        while self.connections:
            self.connections.pop()

    def discard_path(self, path: str) -> None:
        """
        Method to discard deleted file path.
        :param path:
            Deleted file path.
        :return:
        """
        self.paths.pop(path)

    def add_path(self, path: str) -> None:
        """
        Method to add created file path.
        :param path:
            Created file path.
        """
        self.paths.append(path)

    def discard_channel(self, channel: str) -> None:
        """
        Method to discard channel that has gone down.
        :param channel:
            Channel that has gone down.
                ex) http://host:port
        """
        self.channels.pop(channel)

    def add_channel(self, channel: str) -> None:
        """
        Method to add newly opened channel.
        :param channel:
        :return:
        """
        self.channels.append(channel)

    @property
    def shape(self):
        shape = {
            self.project: {
                "paths": self.paths,
                "channels": self.channels
            }
        }
        return shape

    @property
    def key(self) -> str:
        """
        Key property to use the identify watch.
        """
        return self.project

    def __eq__(self, manager) -> bool:  # type: ignore
        return self.key == manager.key

    def __ne__(self, manager) -> bool:  # type: ignore
        return self.key != manager.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        return "<%s: project=%s>" % (
            type(self).__name__, self.key)


class HTTPManager(_Manager):

    __http_options__ = ("headers", "http_auth", "timeout",
                        "keepalive_timeout", "total_connection")

    def __init__(self,
                 project: str,
                 loop: Loop,
                 **kwargs):
        super().__init__(project, loop)
        self.dead_count = {}
        self.kwargs = kwargs

    def set_connection(self, connection_class):

        loop = self._loop
        http_option = {ho: self.kwargs[ho]
                       for ho in self.__http_options__ if ho in self.kwargs}
        for channel in self.channels:
            self.connections.append(
                connection_class(loop, channel, **http_option))


class SSHManager(_Manager):

    def __init__(self, proj, loop):
        super().__init__(proj, loop)

    def set_connection(self, connection_class):
        pass

