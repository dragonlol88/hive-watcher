import json
import time
import queue
import asyncio
import io
from watcher.wrapper.stream import get_file_io
from watcher.wrapper.stream import AsyncJson
from watcher.wrapper.stream import AsyncFileIO
from watcher.hivewatcher import Watch
from watcher.common import WatchIO
from watcher.hivewatcher import HiveWatcher
from watcher.supervisor import Supervisor
from watcher.hivewatcher import HiveEventEmitter
from watcher.notify import RemoteNotify
from watcher.utils import get_running_loop
import functools
import contextvars


if __name__ == '__main__':
    watch_path = './data/watch.json'
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
                loop_kind,
                localnotify_root_dir,
                localnotify_ignore_pattern,
                proj_depth=1,
                timeout=timeout,
                record_interval_minute=0.3,
                max_event=None
                 )

    s = Supervisor(hw, reload_interval=1/3600*24, max_event=30)

    s.watch()

# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#
#     loopa = asyncio.get_event_loop()
#     event_queue = queue.Queue()
#     print(loopa==loop)
#     watches = {}
#     emiter = HiveEventEmitter(loop,
#                               event_queue,
#                               watches,
#                               loop.create_task,
#                               localnotify_root_dir="../test-config",
#                               localnotify_ignore_pattern='.*swp|4913|.*~|.*swx:',
#                               localnotify_proj_depth=1,
#                               remotenotify_host='127.0.0.1',
#                               remotenotify_port=7777)
#     emiter.start()
#
#     async def timer():
#         while True:
#             await asyncio.sleep(2)
#
#     async def start():
#         tasks = []
#         while True:
#             try:
#                 task, event = event_queue.get(timeout=0)
#                 print(task)
#                 await asyncio.sleep(1)
#                 # await task
#                 # print(event)
#             except queue.Empty:
#                 pass
#             # task = loop.create_task(event())
#
#             # print(event)
#             # task = loop.create_task(event())
#             # await task
#             # time.sleep(0.5)
#         # loop.run_until_complete(start())
#         # a = await asyncio.gather(*tasks)
#     loop.run_until_complete(start())