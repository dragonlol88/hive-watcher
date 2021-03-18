import aiohttp
import urllib3
import typing as t

from watcher.type import Loop
from watcher.utils import get_running_loop


class Session:

    session_class = aiohttp.ClientSession

    def __init__(self,
                 *,
                 loop: Loop,
                 headers: t.Optional[t.Dict[str, str]] = {},
                 http_auth: t.Optional[t.Tuple[str, str]] = None,
                 timeout: t.Optional[float] = 300,
                 read_timeout: t.Optional[float] = 300,
                 keepalive_timeout: t.Optional[float] = 15,
                 total_connections: t.Optional[float] = 30,
                 **kwargs
                 ):

        if not headers:
            headers = {}

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
                http_auth = ":".join(http_auth)                                                           # type: ignore
            headers.update(urllib3.make_headers(basic_auth=http_auth))

        if self.keepalive_timeout:
            keep_alive = 'timeout=%d, max=%d' % \
                         (self.keepalive_timeout, self.total_connections)                                 # type: ignore

            headers.update({'keep-alive':keep_alive})

        self.headers = headers
        self._create_session()

    async def request(self,
                      method: str,
                      url: str,
                      *,
                      headers: t.Dict[str, str] = None,
                      data: t.Optional[t.Union[bytes, t.AsyncGenerator]] = None,
                      body: t.Optional[t.Union[t.Any, bytes]] = None) -> t.Any:

        options = {}
        if headers:
            self.headers.update(headers)


        if data:
            options.update({'data': data})
        if body:
            options.update({'body': body})

        method = method.lower()

        if not hasattr(self.session, method):
            raise AttributeError

        command = getattr(self.session, method)

        try:
            async with command(url, **options) as resp:
                response = await resp.text()
        except Exception as e:
            raise e

        return response

    def _create_session(self) -> None:

        if not self.loop:
            self.loop = get_running_loop()

        self.session = self.session_class(
                                    loop=self.loop,
                                    auto_decompress=self.auto_decompress,
                                    headers=self.headers
                                    )

    async def close(self) -> None:
        """
        Close session
        :return:
        """
        await self.session.close()
