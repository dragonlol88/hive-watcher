import asyncio

from . import common as c
from .wrapper.stream import AsyncJson
from collections import defaultdict


class ActionBase:

    # prt : prototype

    def __init__(self, **prt):

        self.prt = prt
        self.ssh_exe = None
        for k, v in self.prt.items():
            setattr(self, k, v)

        """
            {
                'method': '',
                'kwargs': {},
            }
        """
    def connect_ssh_exe(self, ssh_exe):
        self.ssh_exe = ssh_exe

    def action(self):
        if not hasattr(self, "methods"):
            raise AttributeError("methods attribute must be specified.")
        resp = []
        for method in self.methods:
            action = getattr(self, method.strip("_"))
            resp.append(action())

        return resp


class ElasticsearchAction(ActionBase):

    open_ = f"curl -POST 'localhost:%(port)s/%(index)s/_open'"
    close_ = f"curl -POST 'localhost:%(port)s/%(index)s/_close'"

    def __init__(self, ssh_exe, prt):
        super().__init__(ssh_exe, prt)

    def open(self):
        command = self.open_ % self.__dict__
        return self.ssh_exe(command)

    def close(self):
        command = self.close_ % self.__dict__
        return self.ssh_exe(command)


class DockerAction(ActionBase):
    restart_ = 'docker restart %(container)s'

    def __init__(self, ssh_exe, prt):
        super().__init__(ssh_exe, prt)

    def restart(self):
        command = self.restart_ % self.__dict__
        return self.ssh_exe(command)


class Job:
    __slots__ = ('source', 'target', "channel", "actions", "user")

    def __init__(self, source, channel, actions=None, user=None, target=None):
        self.source = source
        self.target = target
        self.channel = channel
        self.actions = actions
        self.user = user

    @property
    def key(self):
        """
        Key property to use the identify watch.
        """
        return self.source, self.channel

    def __contains__(self, item):
        return item in self.key

    def __eq__(self, job) -> bool:  # type: ignore
        return self.key==job.key

    def __ne__(self, job) -> bool:  # type: ignore
        return self.key!=job.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        return "<%s: Job=%s>" % (
            type(self).__name__, self.key)


class JobFactory:
    job = Job

    @classmethod
    def create_job(cls, job):
        pass



class WatchBee(object):

    max_fail_num = 3
    BEE_ACTIONS = {
        'elasticsearch': ElasticsearchAction,
        'docker': DockerAction
    }

    BEE_CALLBACKS = {
        c.EventSentinel.CHANNEL_DELETED: c.DELETE_JOBS,
        c.EventSentinel.CHANNEL_CREATED: c.ADD_CHANNEL,
        c.EventSentinel.FILE_DELETED: c.DELETE_JOBS,
        c.EventSentinel.FILE_CREATED: c.ADD_PATH
    }
    # target directory도 지정...

    def __init__(self, project, loop):

        self.project = project
        self.dead_count = defaultdict(int)
        self.jobs = defaultdict(dict)
        self.wait_sources = set()
        self.wait_channels = set()

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

    @property
    def sources(self):
        return [src for (src, chan), _ in self.jobs.key()]

    @property
    def channels(self):
        return [chan for (src, chan), _ in self.jobs.key()]

    def modify_job(self):
        pass

    def delete_job(self, sign):

        for key, job in self.jobs:
            if sign in job:
                del self.jobs[key]

    def create_job(self, resume) -> None:
        a = {
            "type": "ssh",
            "user": "",
            "target": "",
            "source": "",
            "channel": "",
            "actions": ""
        }

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


class BeeManager:
    bee_class = WatchBee

    def __init__(self, config):
        self.async_json = AsyncJson(config.bee_init_path)
        self.watch_pool = None
        self.raw_json = {}

    @property
    def watch_bees(self):
        return self.watch_pool.watch_bees

    async def create_bee_from_config(self):

        raw_json = await self.read()

        projects = raw_json["projects"]
        actions = raw_json["actions"]


    def set_watch_pool(self, watch_pool):
        self.watch_pool = watch_pool

    def register_bee(self, project):

        loop = asyncio.get_event_loop()
        self.watch_bees[project] = WatchBee(project, loop)
        return self.watch_bees[project]

    def find_bee(self, project):
        # 이전에 등록을 해줘야 함
        # create file, modified files (project source)
        # create channel , delete channel

        try:
            bee = self.watch_bees[project]
        except KeyError:
            bee = None
        return bee

    async def read(self):
        return await self.async_json.load()

    async def write(self):
        pass


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


class Data(_H11PacketItem):
    __key__ = 'data'

    def send(self, data):
        self.send_packet[self.__key__] = data

    def receive(self, data):
        self.receive_packet[self.__key__] = data


class Headers(Data):
    __key__ = "headers"

    def send(self, data):
        if self.__key__ in self.send_packet:
            self.send_packet[self.__key__].update(data)
        else:
            self.send_packet[self.__key__] = data


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