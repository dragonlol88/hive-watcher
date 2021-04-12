import os
import asyncio
import aiohttp
import urllib3
import typing as t

from . import common as c
from . import exceptions as e
from . import watchbee
from .wrapper.stream import stream

from aiohttp.client_exceptions import ClientConnectionError


class _Protocol(object):

    def __init__(self, loop, config, **kwargs):
        self.loop = loop
        self.config = config
        self._done = False

    def connection_made(self, transport):
        self._transport = transport

    def receive_event(self, channel, typ, path):
        raise NotImplementedError

    def close(self):
        pass

    @property
    def done(self):
        return self._done

    def _raise_error(self, status_code, raw_data):
        pass


class H11Protocol(_Protocol):

    connection_class = aiohttp.ClientSession
    method = 'POST'

    def __init__(self,
                 loop: c.Loop,
                 config,
                 *,
                 headers: t.Dict[str, str] = {},
                 http_auth: t.Optional[t.Union[t.Tuple[str, str],str]] = None,
                 timeout: float = 300,
                 read_timeout: float = 300,
                 keepalive_timeout: float = 15,
                 total_connections: float = 30,
                 **kwargs
                 ):
        super().__init__(loop, config)
        if not headers:
            headers = {}
        self._loop = loop
        self.timeout = timeout or 300
        self.read_timeout = read_timeout or 300
        self.keepalive_timeout = keepalive_timeout
        self.total_connections = total_connections
        self.params = kwargs
        self.use_dns_cache = self.params.get("use_dns_cache", True)
        self.auto_decompress = self.params.get('auto_decompress', True)

        if http_auth is not None:
            if isinstance(http_auth, (tuple, list)):
                http_auth = ":".join(http_auth)
            headers.update(urllib3.make_headers(basic_auth=http_auth))
        if self.keepalive_timeout:
            keep_alive = 'timeout=%d, max=%d' % \
                         (self.keepalive_timeout, self.total_connections)
            headers.update({'keep-alive': keep_alive})
        self.headers = headers

        self.connection = self._create_connection()

    def _create_connection(self):
        if not self._loop:
            self._loop = c.get_running_loop()

        connection = self.connection_class(
                                        loop=self.loop,
                                        auto_decompress=self.auto_decompress,
                                        headers=self.headers
                                    )

        return connection

    def receive_event(self, channel, typ, path):
        loop = self._loop
        method = self.method
        h11packet = self._transport.read_packet(typ, path, method)
        h11packet.update({"url": channel})
        return loop.create_task(self.transport(h11packet))

    async def transport(self, packet) -> t.Any:
        packet = packet.packet
        address = packet.get('url')
        try:
            async with self.connection.request(**packet) as resp:
                raw_data = await resp.read()
                status_code = resp.status
                headers = resp.headers

        except Exception as exc:
            if isinstance(exc, ClientConnectionError):
                raise ConnectionError("N/A", address, exc, str(exc))
            elif isinstance(e, asyncio.exceptions.TimeoutError):
                raise e.ConnectionTimeout("TIMEOUT", address, exc, str(exc))
            raise e.TransportError("N/A", address, exc, str(exc))

        self._transport.write_from_packet(raw_data, status_code, headers)

        if status_code >= 400:
            self._raise_error(status_code, raw_data)

    def shutdown(self) -> None:
        self._loop.create_task(self.connection.close())

class SSHProtocol(_Protocol):

    def __init__(self, loop):
        super().__init__(loop)

    async def transport(self):
        pass

    async def close(self):
        pass


