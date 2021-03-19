import typing as t

from . import HandlerBase


class ChannelCreateHandler(HandlerBase):

    def __init__(self, event: 'Event'):                                                       # type: ignore
        super().__init__(event)
        self.watch = event.watch
        self.client_host = self.event.target

    async def handle(self) -> None:
        """

        :return:
        """

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """
        self.watch.add_channel(self.client_host)
        return response


class ChannelDeleteHandler(HandlerBase):

    def __init__(self, event: 'Event'):                                                        # type: ignore
        super().__init__(event)
        self.watch = event.watch
        self.client_host = self.event.target

    def event_action(self, response: t.Any) -> t.Any:
        """
        Method to handle event synchronously
        :return:
        """
        return response

    async def handle(self) -> None:

        self.watch.discard_channel(self.client_host)