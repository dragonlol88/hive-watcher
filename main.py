import time
import queue
import asyncio
from watcher.watcher import HiveEventEmitter
from watcher.notify import RemoteNotify

import functools
import contextvars

if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    event_queue = queue.Queue()
    watches = {}
    emiter = HiveEventEmitter(loop,
                              event_queue,
                              watches,
                              loop.create_task,
                              localnotify_root_dir="../test-config",
                              localnotify_ignore_pattern='.*swp|4913|.*~|.*swx:',
                              localnotify_proj_depth=1,
                              remotenotify_host='127.0.0.1',
                              remotenotify_port=7777)
    emiter.start()

    async def timer():
        while True:
            await asyncio.sleep(2)

    async def start():
        tasks = []
        while True:
            try:
                event = event_queue.get()
            except queue.Empty:
                pass
            # task = loop.create_task(event())
            await event
            # task = loop.create_task(event())
            # await task
            # time.sleep(0.5)
        # loop.run_until_complete(start())
        # a = await asyncio.gather(*tasks)
    loop.run_until_complete(start())