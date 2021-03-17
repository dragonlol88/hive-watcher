import urllib3
import typing as t

class HandlerBase:

    # Http Rquest method
    method = 'POST'

    def __init__(self, event):

        self.event = event
        self.event_type = event.event_type


    def event_action(self, response):
        """
        Method to handle event synchronously
        :return:
        """
        return response

    async def handle(self):
        raise NotImplementedError

    async def handle_event(self) -> t.Any:

        try:
            response = await self.handle()

        except Exception as e:
            raise e

        response = self.event_action(response)

        return response
