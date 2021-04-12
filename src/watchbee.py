import os
import copy
import asyncio
import typing as t

from . import common as c
from .wrapper.stream import stream

from collections import defaultdict


class _WatchBee(object):

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

    def connection_made(self, transport):
        raise NotImplementedError

    async def transport_file(self, event_type, path):
        raise NotImplementedError

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

    def schedule_event(self, event):
        event_type, target = event
        coro_events = self.WATCH_INDEX[event_type]
        coro_funcs = self.create_coroutine(coro_events)
        if not coro_funcs:
            event_num = len(coro_events)
            massage = ', '.join(["%s"]*event_num) + "coroutines does not exist"
            raise ValueError(massage % coro_events)

        coros = []
        for coro in coro_funcs:
            if asyncio.iscoroutinefunction(coro):
                coros.append((coro(event_type, target),))
            else:
                coros.append((coro, target))
        return coros

    def create_coroutine(self, coro_events):
        coro_funcs = []
        for coro_event in coro_events:
            if hasattr(self, coro_event):
                coro_funcs.append(self.__dict__[coro_event])
        return coro_funcs

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


class H11WatchBee(_WatchBee):

    __http_options__ = ("headers", "http_auth", "timeout",
                        "keepalive_timeout", "total_connection")
    method = 'POST'

    def __init__(self,
                 project: str,
                 loop: c.Loop,
                 **kwargs):
        super().__init__(project, loop)
        self.dead_count = {}
        self.kwargs = kwargs

    def connection_made(self, transport):
        self.transport = transport
        self.transport.connection_made(self)

    async def transport_file(self, event_type, path):
        h11packet = H11Packet()
        method = self.method
        file_name = os.path.basename(path)
        event_type_num = event_type.value

        if not isinstance(event_type_num, str):
            event_type_num = str(event_type_num)
        if event_type in (c.EventSentinel.FILE_CREATED,
                          c.EventSentinel.FILE_MODIFIED,
                          c.EventSentinel.FILE_DELETED):
            content_type = 'application/octet-stream'
        else:
            raise ValueError("%s not supported event" % (repr(self.event_type)))

        h11packet.Headers.send({
                        "File-Name": file_name,
                        "Event-Type": event_type_num,
                        "Content-Type": content_type
                        })
        h11packet.Data.send(stream(path))
        h11packet.Body.send(b'')
        h11packet.CRUD.send(method)
        h11packet.EOF.send(EOF)
        try:
            self.transport.transport(h11packet)
        except Exception as e:
            pass

    def set_connection(self, connection_class):

        loop = self._loop
        http_option = {ho: self.kwargs[ho]
                       for ho in self.__http_options__ if ho in self.kwargs}
        for channel in self.channels:
            self.connections.append(
                connection_class(loop, channel, **http_option))


class H11Packet:

    def __init__(self):
        self.Headers = Headers(self)
        self.Data = Data(self)
        self.Body = Body(self)
        self.CRUD = CRUD(self)
        self.STATUS = STATUS(self)
        self.EOF = EOF(self)
        self.packet = {}
        self.send =  {}
        self.recieve = {}


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
        return self.packet[self.__slots__]

    def send(self, data):
        raise NotImplementedError

    def receive(self, data):
        raise NotImplementedError


class Headers(_H11PacketItem):
    __slots__ = "headers"

    def send(self, data):
        if 'headers' in self.send_packet:
            self.send_packet['headers'].update(data)
        else:
            self.send_packet['headers'] = data

    def receive(self, data):
        pass


class Data(_H11PacketItem):
    __slots__ = 'data'

    def send(self, data):
        self.send_packet['data'] = data

    def receive(self, data):
        pass


class Body(_H11PacketItem):
    __slots__ = 'body'

    def send(self, data):
        self.send_packet['body'] = data

    def receive(self, data):
        pass


class STATUS(_H11PacketItem):
    __slots__ = 'status_code'

    def send(self, data):
        self.send_packet['status_code'] = data

    def receive(self, data):
        pass


class CRUD(_H11PacketItem):
    __slots__ = 'crud'

    def send(self, data):
        self.send_packet['method'] = data

    def receive(self, data):
        pass


class EOF(_H11PacketItem):
    __slots__ = 'eof'

    def send(self, data):
        self.send_packet['eof'] = data
        self.packet = self.send_packet

    def receive(self, data):
        self.receive_packet['eof'] = data
        self.packet = self.receive_packet