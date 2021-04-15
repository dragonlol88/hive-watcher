import asyncio
import aiohttp
import urllib3
import typing as t

from . import common as c
from . import exceptions as e

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
        self.read_timeout = read_timeout or 300
        self._timeout = timeout or 300
        self.keepalive_timeout = keepalive_timeout
        self.params = kwargs
        self.total_connections = total_connections
        self.use_dns_cache = self.params.get("use_dns_cache", True)

        if http_auth is not None:
            if isinstance(http_auth, (tuple, list)):
                http_auth = ":".join(http_auth)
            headers.update(urllib3.make_headers(basic_auth=http_auth))
        if self.keepalive_timeout:
            keep_alive = 'timeout=%d, max=%d' % \
                         (self.keepalive_timeout, self.total_connections)
            headers.update({'keep-alive': keep_alive})
        self.headers = headers

        self.auto_decompress = self.params.get('auto_decompress', True)
        self.connection = self._create_connection(self.timeout)

    def _create_connection(self, timeout=None):
        if not self._loop:
            self._loop = c.get_running_loop()
        connection = self.connection_class(
                                        loop=self.loop,
                                        auto_decompress=self.auto_decompress,
                                        headers=self.headers,
                                        timeout=self.timeout)

        return connection

    @property
    def timeout(self):
        timeout = self._timeout or 60*5
        return aiohttp.ClientTimeout(total=timeout)

    def receive_event(self, channel, typ, path):
        loop = self._loop
        method = self.method
        h11packet = self._transport.read_packet(typ, path, channel, method)
        task = loop.create_task(self.transport(h11packet))
        task.set_name(channel)
        return task

    async def transport(self, packet) -> t.Any:
        send_packet = packet.send_packet
        address = send_packet.get('url')

        try:
            async with self.connection.request(**send_packet) as resp:
                raw_data = await resp.read()
                status_code = resp.status
                headers = resp.headers
        except Exception as exc:
            print(exc)
            if isinstance(exc, ClientConnectionError):
                raise ConnectionError("N/A", address, exc, str(exc))
            elif isinstance(e, asyncio.exceptions.TimeoutError):
                raise e.ConnectionTimeout("TIMEOUT", address, exc, str(exc))
            raise e.TransportError("N/A", address, exc, str(exc))
        if status_code >= 400:
            self._raise_error(status_code, raw_data)

        self._write_packet(packet, raw_data,
                           headers, status_code)
        return packet

    def _write_packet(self, packet, raw_data, headers, status_code):
        packet.Data.receive(raw_data)
        packet.Headers.receive(headers)
        packet.Status.receive(status_code)
        packet.EOF.receive(c.EOF)
        self._transport.write_packet(packet)

    async def shutdown(self) -> None:
        await self.connection.close()


class SSHProtocol(_Protocol):

    def __init__(self, loop):
        super().__init__(loop)

    async def transport(self):
        pass

    async def close(self):
        pass


