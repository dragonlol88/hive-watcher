import os
import asyncio

from . import loggy
from . import protocols
from . import watch_pool

from .loops.asyncio_loop import asyncio_setup

FILE_NAME = {
            "manager": "managers.py",
            "log"    : "watcher.log",
            "file"   : "files.json"
        }

class Config:

    def __init__(self,
                 mode,  # watcher or agent
                 lookup_dir: str,
                 *,
                 ignore_pattern: str = '.*swp|4913|.*~|.*swx:',
                 log_config=loggy.LOGGING_CONFIG,
                 protocol_type: str = 'h11',
                 noti_host: str = '127.0.0.1',
                 noti_port: int = 6666,
                 use_color: bool = True,
                 project_depth: int = 1,
                 connection_timeout: float = 300,
                 keep_alive_timeout: float = 5.0,
                 queue_timeout: float = 0,
                 record_interval_minute: int = 5,
                 reload_delay: int = 2,
                 reload_interval: int = 7,
                 max_event: int = 400,
                 retry_on_timeout: bool = False,
                 retry_on_status_code: tuple = (500, 503, 504),
                 ssh_deploy_servers: list = [],
                 user_name = None
                 ):

        # mode (watcher or agent)
        self.mode = mode
        self.files = {}
        # local notify parameter
        self.lookup_dir = lookup_dir
        self.ignore_pattern = ignore_pattern
        self.project_depth = project_depth

        # remote notify parameter
        self.noti_host = noti_host
        self.noti_port = noti_port

        # managed files and channel
        self.watchbee_store_path = None
        self.files_store_path = None
        self.record_interval_minute = record_interval_minute

        # request
        self.connection_timeout = connection_timeout
        self.keep_alive_timeout = keep_alive_timeout

        # queue
        self.queue_timeout = queue_timeout

        # reload
        self.reload_delay = reload_delay
        self.reload_interval = reload_interval
        self.max_event = max_event

        # log
        self.log_path = None
        self.log_config = log_config
        self.use_color = use_color

        # ssh
        self.user_name = user_name
        self.ssh_deploy_servers = ssh_deploy_servers

        # connection protocol
        self.protocol_type = protocol_type
        self.protocol_factory = None

        # transporter
        self.retry_on_timeout = retry_on_timeout
        self.retry_status_code = retry_on_status_code
        self.transporter = None

        self.configure_logging()

    def create_pool(self, watcher, event_queue):
        pool = watch_pool.WatchPool(self, event_queue, watcher)
        return pool

    def configure_logging(self):
        pass

    def setup_loop(self):
        pass

    def load(self):
        # transport
        # manager
        # connection

        # mode have two versions which are watcher and agent
        assert self.mode in ['watcher', 'agent']

        # The 'agent' mode have only ssh protocol to deploy files to multiple servers
        # if not, agent only have a role which deploy files in itself server.
        if self.mode == 'agent':
            assert self.protocol_type == 'ssh' or\
                   self.protocol_type is None

        # Connection protocol is defined.
        # Connection HTTP or SSH
        if self.protocol_type is not None:
            if self.protocol_type == 'ssh':
                self.protocol_factory = protocols.SSHProtocol
            else:
                self.protocol_factory = protocols.H11Protocol

        reference = os.getcwd()
        inspect_dir = os.path.join(reference, 'data')
        if not os.path.exists(inspect_dir):
            os.mkdir(inspect_dir)

        self.watchbee_store_path = os.path.join(inspect_dir, 'watchbee.json')
        self.files_store_path=os.path.join(inspect_dir, 'watchbee.json')
        # log_path: str

        # set loop
        asyncio_setup()

        loop = asyncio.get_running_loop()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop



