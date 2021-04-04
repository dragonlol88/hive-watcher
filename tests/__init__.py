import queue
import asyncio
import threading

from watcher.server import HiveServer
from watcher.hivewatcher import HiveEventEmitter


def run_test_server(server_address, watcher_address):

    sv = HiveServer(server_address, watcher_address)
    t = threading.Thread(target=sv.serve, args=(), daemon=True)
    t.start()
    return sv


def run_test_emitter(root_dir, ignore_pattern, proj_depth, host, port):
    loop = asyncio.get_event_loop()
    event_queue = queue.Queue()
    watches = {}
    files = {}
    timeout = 0.4
    emitter = HiveEventEmitter(loop,
                               event_queue,
                               watches,
                               loop.create_task,
                               timeout,
                               localnotify_root_dir=root_dir,
                               localnotify_ignore_pattern=ignore_pattern,
                               localnotify_proj_depth=proj_depth,
                               localnotify_files=files,
                               remotenotify_host=host,
                               remotenotify_port=port)
    emitter.start()

    class WatcherThread(threading.Thread):

        def __init__(self, emitter, loop, event_queue):
            super().__init__()
            self.emitter = emitter
            self.loop = loop
            self.event_queue = event_queue
            self.events = queue.Queue()
            self._complete = threading.Event()
            self.setDaemon(True)

        async def on_start(self):
            self._complete.clear()
            is_complete = self._complete.is_set()
            while not is_complete:
                try:
                    task, event = event_queue.get()
                    self.queue_event(event)
                    await task
                except queue.Empty:
                    pass

                is_complete = self._complete.is_set()

        def get_event(self, timeout=5):
            return self.events.get(timeout=timeout)

        def queue_event(self, event):
            self.events.put(event)

        def close(self):
            self._complete.set()

        def run(self):
            self.loop.run_until_complete(self.on_start())

    wt = WatcherThread(emitter, loop, event_queue)
    wt.start()

    return wt