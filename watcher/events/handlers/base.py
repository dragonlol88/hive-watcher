import re
import logging
import typing as t

from watcher.common import EventStatus
from watcher.type import Loop
from watcher.exceptions import EVENT_ERROR

if t.TYPE_CHECKING:
    from watcher.events import ChannelEventTypes, FileEventTypes
    from watcher.type import Loop

logger = logging.getLogger('watcher')

url_regex = re.compile(r'''
(http://|https://)           # http scheme
(                            # first capture group = Addr
  \[                         # literal open bracket                       IPv6
    [:a-fA-F0-9]+            # one or more of these characters
  \]                         # literal close bracket
  |                          # ALTERNATELY
  (?:                        #                                            IPv4
    \d{1,3}\.                # one to three digits followed by a period
  ){3}                       # ...repeated three times
  \d{1,3}                    # followed by one to three digits
  |                          # ALTERNATELY
  [-a-zA-Z0-9.]+              # one or more hostname chars ([-\w\d\.])      Hostname
)                            # end first capture group
(?:                          
  :                          # a literal :
  (                          # second capture group = PORT
    \d+                      # one or more digits
  )                          # end second capture group
 )?                          # ...or not.''', re.X)

class HandlerBase:

    # Http Request method
    method = 'POST'

    def __init__(self, event: t.Union['ChannelEventTypes', 'FileEventTypes']):

        self.event = event

    @property
    def event_type(self):
        return self.event.event_type

    @property
    def watch(self):
        return self.event.watch

    def event_action(self, response):
        """
        Method to handle event synchronously
        :return:
        """
        return response

    async def handle(self) -> t.List[t.Tuple[str, t.Any, t.Any, t.Any]]:
        raise NotImplementedError

    async def handle_event(self) -> t.Any:
        responses = []
        try:
            responses = await self.handle()
        except Exception as exc:
            self._failure_logs()
            raise exc

        self.event_action(responses)

        errors = []
        event_type = self.event_response[self.event_type]
        for response in responses:
            url, file, status_code, exc = response
            if exc or int(status_code) >= 500:
                errors.append((url, file, status_code, exc))
                self._failure_logs(url,
                                   file,
                                   event_type,
                                   status_code=status_code,
                                   exception=exc)
                continue
            self._success_logs()

        if errors:
            raise EVENT_ERROR[self.event_type]("Cannot transmit %s" % errors[0][1])
        return responses

    @property
    def loop(self) -> Loop:
        """

        :return:
        """
        return self.event.loop

    @property
    async def channels(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for channel in self.watch.channels:
            yield channel

    @property
    async def paths(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for path in self.watch.paths:
            yield path

    def _failure_logs(self, url, file, event_type, status_code=None, exception=None):

        if status_code == 200:
            return
        host, port = self._separate_url(url)
        # time - [event-type] - [fail] - [file] - [host:port]

        proj, file_name = file.split("/")[-2:]
        logger.info(
            "%s - %s's %s transmission is failed [%s:%s]",
            event_type,
            proj,
            file,
            host,
            port,
            extra={'color': "yello"})

        if exception:
            self._log_to_file(event_type, proj, file, host, port, exception)

    def _log_to_file(self, event_type, proj, file, host, port, exception):
        pass

    def _success_logs(self):
        # if status_code == 200:
        #     return
        # host, port = self._separate_url(url)
        # # time - [event-type] - [fail] - [file] - [host:port]
        #
        # proj, file_name = file.split("/")[-2:]
        #
        # error_logger.error(
        #     "%s - %s - %s's %s transmission is failed - %s [%s:%s]",
        #     event_type,
        #     proj,
        #     file,
        #     host,
        #     port)
        pass

    def _separate_url(self, host):
        separated_url = url_regex.match(host)
        host, port = separated_url.group(2,3)
        return host, port


    event_response = {member.value: member.phrase  # type: ignore
                      for member in EventStatus.__members__.values()}