import asyncio
import aiohttp
import urllib3
import typing as t


from .type import Loop
from .utils import get_running_loop
from .exceptions import (
    TransportError,
    ConnectionError,
    ConnectionTimeout
)
from aiohttp.client_exceptions import ClientConnectionError


class Connection(object):

    def __init__(self, loop, **kwargs):
        self.loop = loop
        self._done = False

    async def transport(self, **kwargs):
        pass

    async def close(self):
        pass

    @property
    def done(self):
        return self._done

    def _raise_error(self, status_code, raw_data):
        pass


class HTTPConnection(Connection):

    connection_class = aiohttp.ClientSession

    def __init__(self,
                 loop: Loop,
                 address: str,
                 *,
                 headers: t.Dict[str, str] = {},
                 http_auth: t.Optional[t.Union[t.Tuple[str, str],str]] = None,
                 timeout: float = 300,
                 read_timeout: float = 300,
                 keepalive_timeout: float = 15,
                 total_connections: float = 30,
                 **kwargs
                 ):
        super().__init__(self)
        if not headers:
            headers = {}
        self.address = address
        self.loop = loop
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

        if not self.loop:
            self.loop = get_running_loop()

        self.connection = self.connection_class(
                                        loop=self.loop,
                                        auto_decompress=self.auto_decompress,
                                        headers=self.headers
                                    )

    async def transport(self,
                        method: str,
                        *,
                        headers: t.Dict[str, str] = None,
                        data: t.Optional[t.Union[bytes, t.AsyncGenerator]] = None,
                        body: t.Optional[t.Union[t.Any, bytes]] = None) -> t.Any:

        options = {}
        address = self.address
        if headers:
            self.headers.update(headers)
        if data:
            options.update({'data': data})
        if body:
            options.update({'body': body})
        method = method.lower()
        if not hasattr(self.connection, method):
            raise AttributeError
        command = getattr(self.connection, method)
        try:
            async with command(address, headers=self.headers, **options) as resp:
                raw_data = await resp.read()
                status_code = resp.status
                headers = resp.headers
        except Exception as e:
            if isinstance(e, ClientConnectionError):
                raise ConnectionError("N/A", address, e, str(e))
            elif isinstance(e, asyncio.exceptions.TimeoutError):
                raise ConnectionTimeout("TIMEOUT", address, e, str(e))
            raise TransportError("N/A", address, e, str(e))

        if status_code >= 400:
            self._raise_error(status_code, raw_data)
        return raw_data, headers, status_code

    async def close(self) -> None:
        """
        Close session
        :return:
        """
        await self.connection.close()


class SSHConnection(Connection):

    def __init__(self, loop):
        super().__init__(loop)

    async def transport(self):
        pass

    async def close(self):
        pass
