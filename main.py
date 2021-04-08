
from src.watcher import HiveWatcher
from src.supervisor import Supervisor
from src.loggy import configure_logging
from src.connection import HTTPConnection
if __name__ == '__main__':
    configure_logging()
    watch_path = './data/watch.json'
    files_path = './data/files.json'
    loop_kind = 'asyncio'
    remotenotify_host = '127.0.0.1'
    remotenotify_port = 7777
    localnotify_root_dir = "./data/project"
    localnotify_ignore_pattern = '.*swp|4913|.*~|.*swx:'
    localnotify_proj_depth = 1
    timeout = 0.1
    record_interval_minute = 5
    max_event = None

    hw = HiveWatcher(
                remotenotify_host,
                remotenotify_port,
                watch_path,
                HTTPConnection,
                files_path,
                loop_kind,
                localnotify_root_dir,
                localnotify_ignore_pattern,
                proj_depth=1,
                timeout=timeout,
                record_interval_minute=0.3,
                max_event=None
                 )

    s = Supervisor(hw, reload_interval=1/3600*24, max_event=12000)
    s.watch()
