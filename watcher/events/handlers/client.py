import aiohttp
import urllib3
import typing as t

from watcher.utils import get_running_loop


class Session:

    session_class = aiohttp.ClientSession

    def __init__(self,
                *,
                loop,
                headers: t.Optional[t.Dict[str, str]] = {},
                http_auth: t.Optional[t.Tuple[str, str]]=None,
                timeout: t.Optional[float]=300,
                read_timeout: t.Optional[float]=300,
                keepalive_timeout: t.Optional[float]=15,
                total_connections: t.Optional[float]=30,
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
                http_auth = ":".join(http_auth)
            headers.update(urllib3.make_headers(basic_auth=http_auth))

        if self.keepalive_timeout:
            keep_alive = 'timeout=%d, max=%d' % \
                         (self.keepalive_timeout, self.total_connections)

            headers.update({'keep-alive':keep_alive})

        self.headers = headers

    async def request(self,
                      method,
                      url,
                      *,
                      headers=None,
                      data=None,
                      body=None):

        options = {}
        if headers:
            self.headers.update(headers)

        await self._create_session()

        if data:
            options.update({'data': data})
        if body:
            options.update({'body': body})

        method = method.lower()
        if hasattr(self.session, method):
            method = getattr(self.session, method)

        try:
            async with method(url, **options) as resp:
                response = await resp.text()
        except Exception as e:
            raise e

        return response

    async def _create_session(self) -> None:

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
