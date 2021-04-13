import time
import asyncio
import contextvars
import queue
import threading
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
                 watcher):

        self.watcher = watcher
        self.loop = config.loop
        self.event_queue = event_queue

        self.config = config
        self.protocol_factory = config.protocol_factory
        self.protocol_type = config.protocol_type
        self._record_interval_minute = config.record_interval_minute

        self.watch_bee_class = watchbee.WatchBee

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
        self.__serving_task = loop.create_task(self._serving_forever())
        # pool = await self._start_serving_fut
        # return pool

    def set_watchpool(self):
        if self.protocol_type == 'h11':
            self.protocol_factory = protocols.H11Protocol
        else:
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
            try:
                await event_fut
            ## exception 부분 다시 짜
            except asyncio.CancelledError as exc:
                processor.close()
                raise
            except Exception as exc:
                processor.close()
            finally:
                pass
        except (SystemExit, KeyboardInterrupt) as exc:
            # siginal이랑 연동해서 코드 다시 짜
            raise exc
        return processor

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
        loop = asyncio.get_event_loop()
        if self._should_serving_fut is not None:
            raise RuntimeError(f"watch pool is already being awaited.")

        if self._start_serving_fut is None:
            raise RuntimeError(
                f"{self._serving_forever} method cannot be called directly.")
        self._should_serving_fut = loop.create_future()
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
                if self._record_interval_minute:
                    if time.time() - self.__starttime > self._record_interval_minute:
                        await self._write_bee()
                        self.__starttime = time.time()
                await asyncio.sleep(0)
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
        new_transport = []
        # while waiters:
        #     waiter = waiters.pop()
        #     print(waiter)
        #     if waiter.done() or waiter.cancelled():
        #         waiter.set_result(None)
        #     else:
        #         new_waiters.append(waiter)

        # self._waiter = new_waiters
        while self._transports:
            transport = self._transports.pop()
            if transport._state == c._FINISHED:
                rv = transport.result()
                # if rv.event_complete:
                #     # rv = transport.result()
                #     # print(rv)
                pass
            else:
                new_transport.append(transport)
        self._transports = new_transport

        event = self._read_event()
        if event is None:
            return
        loop = self.loop
        if loop is None:
            raise RuntimeError("loop must be specified.")
        transport = loop.create_task(self._process_event(event))
        self._transports.append(transport)

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
    def __init__(self, loop, pool, event, watch_bee, config=None, waiter=None):
        self._loop = loop
        self._pool = pool
        self._config = config
        self._over_timeout_for_cancel = config._overtimeout_for_cancel
        self._watchbee = watch_bee
        self._state = c._PENDING
        self.process_handle = None
        self._overtime_handles = []

        self.process_handle = self._loop.call_soon(self.process, event)
        if waiter is not None:
            loop.create_task(self._set_result_when_complete(waiter, None))

    async def _set_result_when_complete(self, fut, value):
        if fut.cancelled():
            return
        while True:
            if self._state == c._FINISHED or \
                    self._state == c._CANCELLED:
                fut.set_result(value)
                break
            await asyncio.sleep(0)

    def process(self, event):
        raise NotImplementedError

    def result(self):
        pass

    def cancel(self):
        pass


class _CallbackEventProcess(_EventProcess):

    def __init__(self, loop, pool, event,
                 watch_bee, config=None, waiter=None):
        super().__init__(loop, pool, event,
                         watch_bee, config, waiter)

    def result(self):
        pass

    def process(self, event):

        proj, typ, arg = event
        EVENT_INDEX = self._watchbee.WATCH_INDEX
        if typ not in EVENT_INDEX:
            raise KeyError("%s type must be in watch index" % typ)

        cb_name = EVENT_INDEX[typ]
        try:
            _cb = getattr(self._watchbee, cb_name)
            _cb(arg)
        except Exception as exc:
            raise exc

        self._state = c._FINISHED

    def cancelled(self):
        return self._state == c._CANCELLED

    def cancel(self):
        if self.process_handle is not None:
            if not self.process_handle._cancelled:
                self.process_handle.cancel()


class _TransportH11EventProcess(_EventProcess):

    def __init__(self, loop, pool, event, watch_bee,
                 protocol, config=None, waiter=None):
        self.set_protocol(protocol)
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.call_soon(self._protocol.connection_made, self)
        super().__init__(loop, pool, event, watch_bee,
                         config, waiter)
        self._transfer_tasks = []
        self._packets = []
        self._create_task_failures = []

    def set_protocol(self, protocol):
        self._protocol = protocol
        self.__protocol_connected = True

    def result(self):
        return self._packets

    def write_packet(self, packet):
        self._packets.append(packet)

    def read_packet(self, typ, path, url, method=None):
        # read packet 다시 코딩해야함
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
        h11packet.Method.send(method)
        h11packet.URL.send(url)
        h11packet.EOF.send(c.EOF)
        return h11packet

    def process(self, event):

        watchbee = self._watchbee
        callbacks = watchbee.WATCH_CALLBACK
        proj, tg, typ = event
        exc = None
        if self._state == c._FINISHED:
            raise RuntimeError("process is already complete.")
        if not self.__protocol_connected:
            raise RuntimeError("protocol does not connected.")
        try:
            _cb = getattr(watchbee, callbacks[typ])
        except KeyError:
            _cb = lambda *x: None
        try:
            for channel in watchbee.channels:
                try:
                    task = self._protocol.receive_event(channel, typ, tg)
                    self._loop.call_soon(_cb, tg)
                    if self._over_timeout_for_cancel:
                        self._call_later_for_cancel(task)
                    self._transfer_tasks.append(task)
                except TypeError:
                    self._create_task_failures.append((channel, typ, tg))
                    continue
        except (KeyboardInterrupt, SystemExit) as exc:
            self.__protocol_connected = False
        except Exception as exc:
            self.__protocol_connected = False
        finally:
            if self.__protocol_connected:
                self._loop.create_task(self.finalize_transport(watchbee))
            else:
                self._protocol.shutdown()
            if exc:
                # log 찍어야함
                pass

    def _call_later_for_cancel(self, task):
        self._overtime_handles.append(
            self._loop.call_later(self._over_timeout_for_cancel,
                                  self._cancel_overtime_task, task))

    def _cancel_overtime_task(self, task):
        if task._state == c._CANCELLED:
            return
        task.cancel()

    async def finalize_transport(self, watchbee):
        while not self._state == c._PENDING:
            tasks_count = len(self._transfer_tasks)
            for _ in range(tasks_count):
                transfer_task = self._transfer_tasks.pop()
                transfer_task_state = transfer_task._state
                if transfer_task_state == c._FINISHED:
                    exception = transfer_task.exception()
                    ch = transfer_task.get_name()
                    if exception:
                        watchbee.mark_dead(ch)
                    else:
                        ch = transfer_task.get_name()
                        watchbee.mark_live(ch)
                elif transfer_task_state == c._PENDING:
                    self._transfer_tasks.append(transfer_task)
            if tasks_count == 0:
                break
            await asyncio.sleep(0)
        self._cancel_overtime_handles()
        await self._protocol.shutdown()
        self.__protocol_connected = False
        self._state = c._FINISHED

    def _cancel_transfer_tasks(self):
        for task in self._transfer_tasks:
            if not task._cancelled:
                task.cancel()
        self._transfer_tasks = []

    def _cancel_overtime_handles(self):
        for handle in self._overtime_handles:
            if not handle._cancelled:
                handle.cancel()
        self._overtime_handles = []

    def finished(self):
        return self._state == c._FINISHED

    def cancelled(self):
        return self._state == c._CANCELLED

    def cancel(self):
        if not self._state == c._CANCELLED:
            self._state = c._CANCELLED
            if self.process_handle is not None:
                if not self.process_handle._cancelled:
                    self.process_handle.cancel()
            self._cancel_transfer_tasks()
            self._cancel_overtime_handles()
        self.__protocol_connected = False