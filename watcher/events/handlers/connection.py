import os
import typing as t

from . import HandlerBase
from .file import stream

if t.TYPE_CHECKING:
    from ..connection import CreateChannelEvent
    from ..connection import DeleteChannelEvent


class ChannelCreateHandler(HandlerBase):

    def __init__(self, event: 'CreateChannelEvent', **kwargs):
        super().__init__(event)


    @property
    def client_address(self):
        return self.event.target

    @property
    def connector(self):
        return self.event.connector

    async def handle(self):
        """

        :return:
        """
        headers: t.Dict[str, str] = {}
        lens = []
        paths = []
        data = b''
        int_to_str_size = 0
        responses = []
        async for path in self.paths:
            try:
                chunks = []
                _stream = stream(path)
                _is_stop = False
                paths.append(path)
                while not _is_stop:
                    try:
                        next_stream = _stream.__anext__()
                        chunk = await next_stream
                        chunks.append(chunk)
                    except StopAsyncIteration:
                        _is_stop = True
                data_per_file = b''.join(chunks)
                int_to_str_size += len(data_per_file)
                lens.append(int_to_str_size)
                data += data_per_file
                responses.append((self.client_address, path, 200, None))
            except Exception as e:
                responses.append((self.client_address, path, None, e))

        if not data:
            self.connector.inject_data(data, header=headers)
            return

        positions = ','.join([str(len) for len in lens])
        path_to_str = ','.join([os.path.basename(path) for path in paths])
        headers.update({
                    "Files-Position": positions,
                    "File-Name": path_to_str
                    })
        self.connector.inject_data(data, header=headers)

        return responses

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """

        self.watch.add_channel(self.client_address)
        return response


class ChannelDeleteHandler(HandlerBase):

    def __init__(self, event: 'DeleteChannelEvent'):
        super().__init__(event)

    @property
    def client_address(self):
        return self.event.target

    async def handle(self):

        return [(self.client_address, None, None, None)]

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """
        self.watch.discard_channel(self.client_address)
        return response

