import asyncio

from . import common as c
from collections import defaultdict


class WatchBee(object):

    max_fail_num = 3
    WATCH_CALLBACK = {
        c.EventSentinel.DELETE_CHANNEL: c.DISCARD_CHANNEL,
        c.EventSentinel.CREATE_CHANNEL: c.ADD_CHANNEL,
        c.EventSentinel.FILE_DELETED: c.DISCARD_PATH,
        c.EventSentinel.FILE_CREATED: c.ADD_PATH
    }

    def __init__(self, project, loop):

        self.project = project
        self.paths = c.UniqueList()
        self.channels = c.UniqueList()  # {"http://127.0.0.1:6666/", "http://192.168.0.230:5112/
        self.channels.append("http://127.0.0.1:6666/")
        self.dead_count = defaultdict(int)
        self.connections = []

        self._loop = loop
        self._lock = asyncio.Lock(loop=self._loop)
        self.transport = None

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
            #log찍
        self.dead_count[channel] = dead_count + 1
    def clear_connection(self):
        while self.connections:
            self.connections.pop()

    def add_path(self, path: str) -> None:
        self.paths.append(path)

    def discard_path(self, path: str) -> None:
        self.paths.pop(path)

    def add_channel(self, channel: str) -> None:
        self.channels.append(channel)

    def discard_channel(self, channel: str) -> None:
        self.channels.pop(channel)

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


class H11Packet:

    def __init__(self):
        self.packet = {}
        self.send_packet = {}
        self.receive_packet = {}
        self.Headers = Headers(self)
        self.Data = Data(self)
        self.Status = Status(self)
        self.Method = Method(self)
        self.URL = URL(self)
        self.EOF = EOF(self)



class _H11PacketItem:

    def __init__(self, packet):
        self.parent_packet = packet
        self.packet = packet.packet
        self.send_packet = packet.send_packet
        self.receive_packet = packet.receive_packet

    def info(self):
        packet_value = self.packet.get(self.__slots__, None)
        if not packet_value:
            state = c._PENDING
        else:
            state = c._FINISHED

    def get(self):
        return self.packet[self.__key__]

    def send(self, data):
        raise NotImplementedError

    def receive(self, data):
        raise NotImplementedError


class Headers(_H11PacketItem):
    __key__ = "headers"

    def send(self, data):
        if self.__key__ in self.send_packet:
            self.send_packet[self.__key__].update(data)
        else:
            self.send_packet[self.__key__] = data

    def receive(self, data):
        self.receive_packet[self.__key__] = data


class Data(_H11PacketItem):
    __key__ = 'data'

    def send(self, data):
        self.send_packet[self.__key__] = data

    def receive(self, data):
        self.receive_packet[self.__key__] = data


class Json(Data):
    __key__ = 'json'


class Status(Data):
    __key__ = 'status_code'


class Method(Data):
    __key__ = 'method'


class URL(Data):
    __key__ = 'url'


class EOF(_H11PacketItem):
    __key__ = 'eof'

    def send(self, data):
        self.packet = self.send_packet
        self.send_packet = {}

    def receive(self, data):
        self.packet = self.receive_packet
        self.receive_packet = {}