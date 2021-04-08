import typing as t
from .exceptions import (
    TransportError,
    ConnectionError,
    ConnectionTimeout
)


class Transporter(object):

    def __init__(self,
                 connection_class,
                 retry_on_timeout=False,
                 retry_status_code=(500, 503, 504),
                 **kwargs):

        self.connection_class = connection_class
        self.retry_on_timeout = retry_on_timeout
        self.retry_status_code = retry_status_code
        self.manager = None
        self.kwargs = kwargs

    def mark_live(self, connection):
        address = connection.address
        self.manager.mark_live(address)

    def mark_dead(self, connection):
        address = connection.address
        self.manager.mark_dead(address)

    def set_manager(self, manager):
        self.manager = manager

    def _set_connections(self):
        if self.manager is None:
            raise ValueError("pool manager must be specified")
        self.manager.set_connection(self.connection_class)

    @staticmethod
    def _deserialize_response(raw_data, header):
        header = header
        return raw_data

    async def transport(self, **packet):
        responses = []
        success = True

        self._set_connections()
        async for connection in self.connections:
            try:
                raw_data, headers, status_code = await connection.transport(**packet)
            except TransportError as e:
                retry = False
                success = False
                exc = e

                if isinstance(e, ConnectionError):
                    retry = True
                elif isinstance(e, ConnectionTimeout):
                    retry = self.retry_on_timeout
                elif e.status_code in self.retry_status_code:
                    retry = True

                self.mark_dead(connection)
                if retry:
                    try:
                        raw_data, headers, status_code = await connection.transport(**packet)
                    except TransportError as e:
                        pass
                    else:
                        self.mark_live(connection)
                        success = True
            finally:
                await connection.close()
                self.manager.clear_connection()
                if not success:
                    raise exc
                data = self._deserialize_response(raw_data, headers)
                responses.append(data)

        return responses

    @property
    async def connections(self) -> t.AsyncGenerator:
        connections = self.manager.get_connections()
        for connection in connections:
            yield connection

    async def close(self):
        async for connection in self.connections:
            await connection.close()






