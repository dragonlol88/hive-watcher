import os
import time
from watcher.handler.local_file import FileModifiedHandler, FileCreatedHandler, FileDeletedHandler
from watcher.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent, CreateChannelEevent, DeleteChannelEevent
from watcher.watcher import HiveEventEmitter
import threading
import asyncio
import threading
import queue
import functools
import contextvars

if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    event_queue = queue.Queue()
    watches = {}
    emiter = HiveEventEmitter("../test-config", event_queue, watches, 1, '.*swp|4913|.*~|.*swx:', loop, loop.create_task)
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