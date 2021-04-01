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
        self.connector = event.connector
        self.client_address = event.target

    async def handle(self) -> None:
        """

        :return:
        """
        headers: t.Dict[str, str] = {}
        lens = []
        paths = []
        data = b''
        int_to_str_size = 0
        async for path in self.paths:
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

        return

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
        self.watch = event.watch
        self.client_address = self.event.target

    async def handle(self) -> None:
        pass

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """
        self.watch.discard_channel(self.client_address)
        return response

