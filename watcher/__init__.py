import queue
import threading
from enum import IntEnum

DEFAULT_QUEUE_TIMEOUT = 1
QUEUE_MAX_SIZE = 4200


class EventStatus(IntEnum):
    FILE_DELETED   = 1
    FILE_CREATED   = 2
    FILE_MODIFIED  = 3
    CREATE_CHANNEL = 4
    DELETE_CHANNEL = 5


class EventQueue(queue.Queue):

    def __init__(self, maxsize=QUEUE_MAX_SIZE):
        super().__init__(maxsize)


class BaseThread(threading.Thread):
    """ Convenience class for creating stoppable threads. """

    def __init__(self):
        threading.Thread.__init__(self)
        if hasattr(self, 'daemon'):
            self.daemon = True
        else:
            self.setDaemon(True)
        self._stopped_event = threading.Event()

        if not hasattr(self._stopped_event, 'is_set'):
            self._stopped_event.is_set = self._stopped_event.isSet

    @property
    def stopped_event(self):
        return self._stopped_event

    def should_keep_running(self) -> bool:
        """Determines whether the thread should continue running."""
        return not self._stopped_event.is_set()

    def on_thread_stop(self):
        """Override this method instead of :meth:`stop()`.
        :meth:`stop()` calls this method.
        This method is called immediately after the thread is signaled to stop.
        """
        pass

    def stop(self) -> None:
        """Signals the thread to stop."""
        self._stopped_event.set()
        self.on_thread_stop()

    def on_thread_start(self) -> None:
        """Override this method instead of :meth:`start()`. :meth:`start()`
        calls this method.
        This method is called right before this thread is started and this
        object’s run() method is invoked.
        """
        pass

    def start(self) -> None:
        self.on_thread_start()
        threading.Thread.start(self)