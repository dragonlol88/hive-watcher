import time
import asyncio
import os
import queue

from . import common as c
from . import exceptions as e
from . import watchbee
from . import protocols

from .wrapper.stream import stream

CHANNEL_DELETED = c.EventSentinel.DELETE_CHANNEL
CHANNEL_CREATED = c.EventSentinel.CREATE_CHANNEL
FILE_DELETED = c.EventSentinel.FILE_DELETED
FILE_CREATED = c.EventSentinel.FILE_CREATED
FILE_MODIFIED = c.EventSentinel.FILE_MODIFIED


class WatchPool(object):

    def __init__(self,
                 config,
                 event_queue,
                 watcher):

        self.watcher = watcher
        self.watcher_state = watcher.state
        self.loop = config.loop
        self.event_queue = event_queue

        self.config = config
        self.protocol_factory = config.protocol_factory
        self.protocol_type = config.protocol_type
        self._record_interval_minute = config.record_interval_minute
        self._over_timeout_for_cancel = config.overtimeout_for_cancel

        self.watch_bee_class = watchbee.WatchBee

        self._waiter = []
        self._process_wrappers = []
        self._processes = watcher.state.processes
        self._time_from_reload = watcher.state.time_from_reload
        self._total_event = watcher.state.total_event

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
        return _TransportH11EventProcess(loop, self, event, watch_bee=watchbee,
                                         protocol=protocol, config=config, waiter=waiter)

    def _finish_callback_event(self, loop, event,
                               watchbee, config=None, waiter=None):
        return _CallbackEventProcess(loop, self, event, watch_bee=watchbee,
                                     config=config, waiter=waiter)

    def _finish_event(self, event, event_fut):
        pj, tg, tp = event
        watchbee = self._get_watch_bee(pj, tp)
        loop = self.loop
        config = self.config
        if tp in (CHANNEL_DELETED, FILE_DELETED):
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
                raise exc
            except Exception as exc:
                processor.close()
                raise exc
            finally:
                pass
        except (SystemExit, KeyboardInterrupt) as exc:
            # siginal이랑 연동해서 코드 다시 짜
            raise exc
        return processor

    def _get_watch_bee(self, pj, tp):
        loop = asyncio.get_event_loop()
        if tp in (CHANNEL_DELETED, CHANNEL_CREATED) and \
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
        new_event_processes = []
        for event_process in self._process_wrappers:
            # _proces_event 에러 처리 다시 생각하기
            try:
                process = event_process.result()
            except asyncio.InvalidStateError:
                new_event_processes.append(event_process)
            except Exception as exc:
                continue
            else:
                self._processes.append(process)
        self._process_wrappers = new_event_processes

        cur_process_size = len(self._processes)
        while cur_process_size > 0:
            cur_process_size -= 1
            process = self._processes.pop()
            if process._state == c._PENDING:
                if time.time() - process.start > self._over_timeout_for_cancel:
                    process.cancel()
                    continue
                self._processes.append(process)

        event = self._read_event()
        if event is None:
            return

        loop = self.loop
        if loop is None:
            raise RuntimeError("loop must be specified.")
        process_wrapper = loop.create_task(self._process_event(event))
        self._process_wrappers.append(process_wrapper)
        self._total_event += 1

    def _detach(self):
        pass

    def _attach(self):
        pass

    async def stop(self):
        # consuming event
        event = self._read_event()
        while event:
            await self._process_event(event)
            event = self._read_event()

        self.__stop_running = True
        await self._write_bee()

        if not self._should_serving_fut and not self._should_serving_fut.done():
            self._should_serving_fut.cancel()

        self._start_serving_fut.cancel()
        self._start_serving_fut = None

    async def _write_bee(self):
        pass

    async def _read_bee(self):
        pass


def _cancel_task(task):
    if task._state == c._CANCELLED:
        return
    task.cancel()


class _EventProcess:
    def __init__(self, loop, pool, event, watch_bee, config=None, waiter=None):
        self._loop = loop
        self._pool = pool
        self._config = config
        self._over_timeout_for_cancel = config.overtimeout_for_cancel
        self._watchbee = watch_bee
        self._state = c._PENDING
        self.process_handle = None
        self._waiter = waiter
        self.start = time.time()
        self._message = None
        self.process_handle = self._loop.call_soon(self.process, event)
        if waiter is not None:
            loop.create_task(
                self._set_result_when_complete(waiter, self._message))

    async def _set_result_when_complete(self, fut, msg, value=None):
        if fut.cancelled():
            return
        while True:
            if self._state == c._FINISHED:
                fut.set_result(value)
                break
            elif msg:
                fut.cancel(msg)
            await asyncio.sleep(0)

    def result(self):
        pass

    def _mark_live_with_bee(self, channel):
        self._watchbee.mark_live(channel)

    def _mark_dead_with_bee(self, channel):
        self._watchbee.mark_dead(channel)

    def finished(self):
        return self._state == c._FINISHED

    def cancelled(self):
        return self._state == c._CANCELLED

    def process(self, event):
        raise NotImplementedError

    def _cancel_transfer_tasks(self):
        raise NotImplementedError

    def _cancel_overtime_handles(self):
        raise NotImplementedError

    async def finalize_transport(self):
        raise NotImplementedError

    def _inspect_transfer_tasks(self):
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError


class _CallbackEventProcess(_EventProcess):

    def __init__(self, loop, pool, event,
                 watch_bee, config=None, waiter=None):
        super().__init__(loop, pool, event,
                         watch_bee, config, waiter)

    def result(self):
        pass

    def process(self, event):

        proj, tg, typ = event
        callback = self._watchbee.WATCH_CALLBACK
        if typ not in callback:
            raise KeyError("%s type must be in watch index" % typ)

        cb_name = callback[typ]
        try:
            _cb = getattr(self._watchbee, cb_name)
            _cb(tg)
        except Exception as exc:
            raise exc

        self._state = c._FINISHED

    def cancel(self):
        if not self._state == c._CANCELLED:
            self._state = c._CANCELLED
            if self.process_handle is not None:
                if not self.process_handle._cancelled:
                    self.process_handle.cancel()


class _TransportH11EventProcess(_EventProcess):

    def __init__(self, loop, pool, event, watch_bee, protocol, config=None, waiter=None):
        self.set_protocol(protocol)
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.call_soon(self._protocol.connection_made, self)
        super().__init__(loop, pool, event, watch_bee, config, waiter)
        self._transfer_tasks = []
        self._packets = []
        self._task_creation_failures = []

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
        if typ in (FILE_CREATED, FILE_MODIFIED, FILE_DELETED):
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

        watch_bee = self._watchbee

        # tg is channel or path. typ
        # typ is event type
        proj, tg, typ = event
        _bee_actions = watch_bee.BEE_ACTIONS
        channels, paths = [], []
        exc = None
        ov_handle = None

        if isinstance(tg, c.Path):
            channels = watch_bee.channels
            paths = [tg.path]*len(channels)

        elif isinstance(tg, c.Channel) and typ == CHANNEL_CREATED:
            paths = watch_bee.paths
            channels = [tg.channel]*len(paths)

        if self._state == c._FINISHED:
            raise RuntimeError("process is already complete.")
        if not self.__protocol_connected:
            raise RuntimeError("protocol does not connected.")
        try:
            _bee_action = getattr(watch_bee, _bee_actions[typ])
        except KeyError:
            _bee_action = lambda *x: None
        try:
            for channel, path in zip(channels, paths):
                try:
                    task = self._protocol.receive_event(channel, typ, path)
                    self._loop.call_soon(_bee_action, path)
                    if self._over_timeout_for_cancel:
                        ov_handle = self._call_later_for_cancel(task)
                    self._transfer_tasks.append((task, ov_handle))
                except TypeError:
                    self._task_creation_failures.append((channel, typ, path))

            # if all of operations are failed to make the tasks
            # raise cancelled error in self._set_result_when_complete
            if not self._transfer_tasks and channels:
                message = f'All task creations are failed'
                self._raise_cancel_error_in_waiter(message)

        except (KeyboardInterrupt, SystemExit) as exc:
            self.__protocol_connected = False
        except Exception as exc:
            self.__protocol_connected = False
        finally:
            if self.__protocol_connected:
                self._loop.create_task(self.finalize_transport())
            else:
                self._protocol.shutdown()
            if exc:
                pass

    def _call_later_for_cancel(self, task):
        return self._loop.call_later(
                            self._over_timeout_for_cancel, task.cancel)

    def _inspect_transfer_tasks(self):
        # 다시 짜야됨

        transfer_task, ov_handle = self._transfer_tasks.pop()
        transfer_task_state = transfer_task._state
        ch = transfer_task.get_name()

        if transfer_task_state == c._CANCELLED:
            # In case of overtime task complete,
            # (that is, transfer task cannot complete in over timeout)
            # raise Runtime error
            self._mark_dead_with_bee(ch)
            raise RuntimeError(f'{transfer_task} was cancelled because of over timeout')

        if transfer_task_state == c._FINISHED:
            # exception 처리 어떻게 하지????
            exception = transfer_task.exception()
            if exception:
                self._mark_dead_with_bee(ch)
                # If transfer task has an error
                # all of related task will be cancelled.
                if ov_handle and self._over_timeout_for_cancel:
                    ov_handle.cancle()
                transfer_task.cancel()
                raise exception

            else:
                self._mark_live_with_bee(ch)
            # cancel overtime handle when transfer task complete.
            ov_handle.cancle()

        elif transfer_task_state == c._PENDING:
            self._transfer_tasks.append((transfer_task, ov_handle))

    def _raise_cancel_error_in_waiter(self, msg=None):
        pass

    async def finalize_transport(self):
        init_task_count = len(self._transfer_tasks)
        while self._state == c._PENDING:
            tasks_count = len(self._transfer_tasks)
            for _ in range(tasks_count):
                try:
                    self._inspect_transfer_tasks()
                except RuntimeError as exc:
                    # log message
                    # because of over timeout
                    print(exc)
                    init_task_count -= 1
                except e.TransportError as exc:
                    # log message
                    # because of transport error
                    init_task_count -= 1
                    print(exc)
            #if all of tasks are cancelled
            if init_task_count == 0:
                self._raise_cancel_error_in_waiter()
            if init_task_count and tasks_count == 0:
                break
            await asyncio.sleep(0)
        await self._protocol.shutdown()
        self.__protocol_connected = False
        if not self.cancelled():
            self._state = c._FINISHED

    def _cancel_transfer_tasks(self):
        for task, ov_handle in self._transfer_tasks:
            if not task._cancelled:
                task.cancel()
            if self._over_timeout_for_cancel and not ov_handle._cancelled:
                ov_handle.cancle()
        self._transfer_tasks = []

    def cancel(self):
        if self._state == c._CANCELLED:
            raise asyncio.InvalidStateError("already cancelled")

        self._state = c._CANCELLED
        if self.process_handle is not None:
            if not self.process_handle._cancelled:
                self.process_handle.cancel()
        self._cancel_transfer_tasks()
        self.__protocol_connected = False