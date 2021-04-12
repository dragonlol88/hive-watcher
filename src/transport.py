import asyncio
import typing as t
import contextvars

from . import exceptions as e
from . import common as c
#
# class Transport(object):
#
#     def __init__(self, loop, pool, protocol, watchbee,
#                  event, config, waiter=None, ):
#
#         self._pool = pool
#         self._watchbee = watchbee
#         self._loop = loop
#         self._event = event
#         self.handle = None
#         self.connections = []
#         self.tasks = []
#         self.config = config
#
#         self.set_protocol(protocol)
#         if loop is None:
#             self._loop = asyncio.get_event_loop()
#         self._loop.call_soon(self._protocol.connection_made, self)
#         self.handle = self._loop.call_soon(self.process, event)
#
#         if waiter is not None:
#             self._loop.call_soon(
#                 asyncio.futures._set_result_unless_cancelled, waiter, None)
#
#     def set_protocol(self, protocol):
#         self._protocol = protocol
#         self.__protocol_connected = True
#
#     def process(self, event):
#         watchbee = self._watchbee
#         WATCH_CALLBACK = watchbee.WATCH_CALLBACK
#         proj, typ, tg = event
#
#         try:
#             cb = WATCH_CALLBACK[typ]
#         except KeyError:
#             cb = None
#         try:
#             for channel in watchbee.channels:
#                 task = self._protocol.receive_event(channel, tg)
#                 if cb is not None:
#                     task.add_done_callback(cb, channel)
#                 self.tasks.append(task)
#         except KeyboardInterrupt:
#             self.__protocol_connected = False
#
#         except Exception:
#             pass
#
#         finally:
#             if self.__protocol_connected:
#                 while self.tasks:
#                     task = self.tasks.pop()
#                     exc = None
#                     if task._state == c._FINISHED:
#                         exc = task.exception()
#                     if exc is not None:
#                         task.cancel()
#                         ch = task.get_name()
#                         watchbee.mark_dead(ch)
#                     if task._state == c._PENDING:
#                            self.tasks.append(task)
#                     else:
#                         ch = task.get_name()
#                         watchbee.mark_live(ch)
#
#             else:
#                 pass
#
#
#
#     def close(self):
#         if self.handle is not None:
#             if not self.handle._cancelled:
#                 self.handle.cancel()
#
#
#
# class H11Transporter(object):
#
#     def __init__(self,
#                  pool,
#                  protocol_class,
#                  watchbee,
#                  retry_on_timeout=False,
#                  retry_status_code=(500, 503, 504),
#                  **kwargs):
#         super().__init__()
#
#         self.pool = pool
#         self._protocol_connected = False
#         self.set_protocol(protocol_class)
#
#         self.watchbee = watchbee
#
#         self.retry_on_timeout = retry_on_timeout
#         self.retry_status_code = retry_status_code
#
#     def set_protocol(self, protocol):
#         self._protocol = protocol
#         self._protocol_connected = True
#
#     async def transport(self, packet):
#         responses = []
#         self._setup_connections()
#         async for connection in self.connections:
#             try:
#                 packet = await connection.transport(packet)
#                 self.mark_live(connection)
#             except e.TransportError as exc:
#                 retry = False
#
#                 if isinstance(exc, ConnectionError):
#                     retry = True
#                 elif isinstance(exc, e.ConnectionTimeout):
#                     retry = self.retry_on_timeout
#                 elif exc.status_code in self.retry_status_code:
#                     retry = True
#
#                 self.mark_dead(connection)
#                 if retry:
#                     try:
#                         packet = await connection.transport(**packet)
#                     except e.TransportError as exc:
#                         raise exc
#                     else:
#                         self.mark_live(connection)
#             finally:
#                 await connection.close()
#                 data = self._deserialize_response(packet)
#                 responses.append(data)
#         self.watch.clear_connection()
#         return responses
#
#
#
#
#
#     def connection_made(self, watch):
#         self.watch = watch
#     def _setup_connections(self):
#         if self.watch is None:
#             raise ValueError("pool manager must be specified")
#         self.watch.set_connection(self.connection_class)
#     @staticmethod
#     def _deserialize_response(raw_data, header):
#         header = header
#         return raw_data
#     @property
#     async def connections(self) -> t.AsyncGenerator:
#         for connection in self.watch.connections:
#             yield connection
#     async def close(self):
#         async for connection in self.connections:
#             await connection.close()
#     def mark_live(self, connection):
#         address = connection.address
#         self.watch.mark_live(address)
#     def mark_dead(self, connection):
#         address = connection.address
#         self.watch.mark_dead(address)
#


