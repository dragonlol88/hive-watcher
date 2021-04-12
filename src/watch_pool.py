import time
import asyncio
import contextvars
import queue
import os
import typing as t

from . import common as c
from . import exceptions as e
from . import watchbee
from . import protocols

from .wrapper.stream import stream

DELETE_CHANNEL = c.EventSentinel.DELETE_CHANNEL
CREATE_CHANNEL = c.EventSentinel.CREATE_CHANNEL
FILE_DELETED = c.EventSentinel.FILE_DELETED


class WatchPool(object):

    def __init__(self,
                 config,
                 event_queue,
                 watcher,
                 loop=None):

        self.watcher = watcher
        self.loop = loop
        self.event_queue = event_queue

        self.config = config
        self.protocol_factory = config.protocol_factory
        self.protocol_type = config.protoco_type
        self._write_period = config.write_period

        self._waiter = []
        self._transports = []
        self.watch_bees = {}
        self.event_count = 0
        self.qtimeout = 0

        self._should_serving_fut = None
        self._start_serving_fut = None
        self.__serving_task = None
        self.__stop_running = False
        self.__starttime = time.time()

        self.set_watchpool()

    async def start(self):
        loop = self.loop
        if loop is None:
            loop = asyncio.get_event_loop()

        self._start_serving_fut = loop.create_future()
        self._should_serving_fut = loop.create_future()
        self.__serving_task = loop.create_task(self._serving_forever())
        pool = await self._start_serving_fut

        return pool

    def set_watchpool(self):
        if self.protocol_type == 'h11':
            self.watch_bee_class = watchbee.H11WatchBee
            self.protocol_factory = protocols.H11Protocol
        else:
            self.watch_bee_class = watchbee.SSHWatchBee
            self.protocol_factory = protocols.SSHProtocol

    def _finish_transport_event(self, loop, protocol, event,
                                watchbee, config, waiter=None):
        return _TransportH11EventProcess(loop, self, event, watchbee,
                                         protocol, config, waiter)

    def _finish_callback_event(self, loop, event,
                               watchbee, config=None, waiter=None):
        return _CallbackEventProcess(loop, self, event, watchbee=watchbee,
                                     config=config, waiter=waiter)

    def _finish_event(self, event, event_fut):
        pj, tg, tp = event
        watchbee = self._get_watch_bee(pj, tp)
        loop = self.loop
        config = self.config
        if tp in (DELETE_CHANNEL, CREATE_CHANNEL,
                  FILE_DELETED):
            processor = self._finish_callback_event(
                loop, event, watchbee, config, event_fut)
        else:
            protocol = self.protocol_factory(loop, config=config)
            processor = self._finish_transport_event(
                loop,  protocol, event, watchbee, config, event_fut)

        return processor

    async def _process_event(self, event):
        try:
            loop = self.loop
            if loop is None:
                loop = asyncio.get_event_loop()
            event_fut = loop.create_future()
            processor = self._finish_event(event, event_fut)
            self._waiter.append(event_fut)
            try:
                await event_fut
            except Exception as exc:
                processor.close()
            finally:
                pass
        except (SystemExit, KeyboardInterrupt):
            raise
        except e.TransportError as exc:
            raise exc

    def _get_watch_bee(self, pj, tp):
        loop = asyncio.get_event_loop()
        if tp in (DELETE_CHANNEL, CREATE_CHANNEL) and \
                pj not in self.watch_bees:
            raise RuntimeError("%s is not created. Add the project first")
        elif pj not in self.watch_bees:
            watch_bee = self.watch_bee_class(pj, loop)
            self.watch_bees[pj] = watch_bee

        return self.watch_bees[pj]

    async def _serving_forever(self):
        if self._should_serving_fut is not None:
            raise RuntimeError(f"watch pool {self} is already being awaited.")

        if self._start_serving_fut is None:
            raise RuntimeError(
                f"{self._serving_forever} method cannot be called directly.")
        await self._read_bee()
        try:
            loop = self.loop
            if loop is None:
                loop = asyncio.get_event_loop()
            asyncio._set_running_loop(loop)
            self._start_serving_fut.set_result(self)
            while True:
                self._run_once()
                if self.__stop_running:
                    break
                if self._write_period:
                    if time.time() - self.__starttime > self._write_period:
                        await self._write_bee()
                        self.__starttime = time.time()
        finally:
            self.__stop_running = False
            asyncio._set_running_loop(None)
            self._should_serving_fut = None

    def _read_event(self):
        qtimeout = self.qtimeout
        try:
            event = self.event_queue.get(timeout=qtimeout)
        except queue.Empty:
            return
        return event

    def _run_once(self):
        waiters = self._waiter
        new_waiters = []
        while waiters:
            waiter = waiters.pop()
            if waiter.done() or waiter.cancelled():
                waiter.set_result(None)
            else:
                new_waiters.append(waiter)
        self._waiter = new_waiters

        while self._transports:
            transport = self._transports.pop()
            rp = transport.result()

        event = self._read_event()
        if event is None:
            return

        trasnport = self._process_event(event)
        loop = self.loop
        if loop is None:
            raise RuntimeError("loop must be specified.")
        loop.create_task(trasnport)
        self._transports.append(trasnport)

    def _detach(self):
        pass

    def _attach(self):
        pass

    def stop(self):
        self.__stop_running = True
        self._write_bee()

        if (self._should_serving_fut is not None and \
                not self._should_serving_fut.done()):
            self._should_serving_fut.cancel()

        self._start_serving_fut.cancel()
        self._start_serving_fut = None

    async def _write_bee(self):
        pass

    async def _read_bee(self):
        pass


class _EventProcess:
    def __init__(self, loop, pool, event, watchbee, config=None, waiter=None):
        self._loop = loop
        self._pool = pool
        self._config = config
        self._watchbee = watchbee
        self.handle = None
        self._state = c._PENDING
        loop = self._loop
        if loop is None:
            self._loop = asyncio.get_event_loop()
        self.handle = self._loop.call_soon(self.process, event)
        if waiter is not None:
            loop.call_soon(
                asyncio.futures._set_result_unless_cancelled, waiter, None)

    def process(self, event):
        raise NotImplementedError

    def result(self):
        pass

    def close(self):
        pass


class _CallbackEventProcess(_EventProcess):

    def __init__(self, loop, pool, event, watchbee, config=None, waiter=None):
        super().__init__(loop, pool, event, watchbee, config, waiter)

    def result(self):
        pass

    def write_packet(self, packet):
        pass

    def read_packet(self, typ, path, method=None):
        pass

    def process(self, event):

        proj, typ, arg = event
        EVENT_INDEX = self._watchbee.WATCH_INDEX
        if typ not in EVENT_INDEX:
            raise KeyError("%s type must be in watch index" % typ)

        cb_name = EVENT_INDEX[typ]
        _cb = getattr(self._watchbee, cb_name)(arg)
        self._state = c._FINISHED

    def close(self):
        if self.handle is not None:
            if not self.handle._cancelled:
                self.handle.cancel()


class _TransportH11EventProcess(_EventProcess):

    def __init__(self, loop, pool, event, watchbee,
                 protocol, config=None, waiter=None):
        self.set_protocol(protocol)
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.call_soon(self._protocol.connection_made, self)
        super().__init__(loop, pool, event, watchbee,
                         config, waiter)
        self.tasks = []
        self.packets = []
        self.__transfer_complete = False

    def set_protocol(self, protocol):
        self._protocol = protocol
        self.__protocol_connected = True

    def result(self):
        return self.packets

    def write_packet(self, packet):
        self.packets.append(packet)

    def read_packet(self, typ, path, method=None):
        h11packet = watchbee.H11Packet()
        file_name = os.path.basename(path)
        event_type_num = typ.value

        if not isinstance(event_type_num, str):
            event_type_num = str(event_type_num)
        if typ in (c.EventSentinel.FILE_CREATED,
                   c.EventSentinel.FILE_MODIFIED,
                   c.EventSentinel.FILE_DELETED):
            content_type = 'application/octet-stream'
        else:
            raise ValueError("%s not supported event" % (repr(typ)))

        h11packet.Headers.send({
            "File-Name": file_name,
            "Event-Type": event_type_num,
            "Content-Type": content_type
        })
        h11packet.Data.send(stream(path))
        h11packet.Body.send(b'')
        h11packet.CRUD.send(method)
        h11packet.EOF.send(c.EOF)
        return h11packet

    def process(self, event):
        watchbee = self._watchbee
        callbacks = watchbee.WATCH_CALLBACK
        proj, typ, tg = event
        if self.__transfer_complete:
            raise RuntimeError("process is already complete.")

        try:
            cb = callbacks[typ]
        except KeyError:
            cb = None
        try:
            for channel in watchbee.channels:
                task = self._protocol.receive_event(channel, typ, tg)
                if cb is not None:
                    task.add_done_callback(cb, tg)
                self.tasks.append(task)
        except KeyboardInterrupt:
            self.__protocol_connected = False
            raise
        except Exception:
            raise

        finally:
            if self.__protocol_connected:
                self._loop.create_task(self.is_complete_transport())
            else:
                pass

            self._protocol.shutdown()
            self.__protocol_connected = False

    async def is_complete_transport(self):
        while self.tasks:
            task = self.tasks.pop()
            exc = None
            if task._state == c._FINISHED:
                exc = task.exception()
            if exc is not None:
                task.cancel()
                ch = task.get_name()
                watchbee.mark_dead(ch)
            if task._state == c._PENDING:
                self.tasks.append(task)
            else:
                ch = task.get_name()
                watchbee.mark_live(ch)
            await asyncio.sleep(0)
        self.__transfer_complete = True

    def close(self):
        if self.handle is not None:
            if not self.handle._cancelled:
                self.handle.cancel()
