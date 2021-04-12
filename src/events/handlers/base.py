import re
import logging
import typing as t

from src.common import EventSentinel
from src.type import Loop
from src.exceptions import EVENT_ERROR
from aiohttp.client_exceptions import ClientConnectionError


logger = logging.getLogger('awatcher')

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

    def __init__(self, event):

        self.event = event


    @property
    def target(self):
        return self.event.target

    @property
    def event_type(self):
        return self.event.event_type

    @property
    def manager(self):
        return self.event.manager

    @property
    def transporter(self):
        return self.event.transporter

    @property
    def loop(self) -> Loop:
        """

        :return:
        """
        return self.event.loop

    @property
    async def paths(self) -> t.AsyncGenerator:
        """

        :return:
        """
        for path in self.manager.paths:
            yield path

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
        event_type = self.event_response[self.event_type]
        try:
            responses = await self.handle()
        except Exception as exc:
            logger.error(
                "%s - %s[%s]",
                event_type,
                self.target,
                str(exc)
            )
            raise exc

        self.event_action(responses)

        errors = []
        for response in responses:
            url, file, status_code, error = response
            if error or int(status_code) >= 500:
                errors.append((url, file, status_code, error))
                self._failure_logs(url,
                                   file,
                                   event_type,
                                   status_code=status_code,
                                   exception=error)
                continue
            self._success_logs(url, file, event_type)

        if errors:
            raise EVENT_ERROR[self.event_type]("Cannot transmit %s" % errors[0][1])
        return responses

    def _failure_logs(self,
                      url: str,
                      file: str,
                      event_type: str,
                      status_code: t.Optional[int] = None,
                      exception: t.Optional[Exception] = None):

        if status_code == 200:
            return
        host, port = self._separate_url(url)
        # time - [event-type] - [fail] - [file] - [host:port]
        proj, file_name = file.split("/")[-2:]
        reason = ''

        if status_code == 500:
            reason = "Internal server error"
        elif isinstance(exception, ClientConnectionError):
            reason = "Server not Found"
        logger.error(
            "%s - %s's %s transmission is failed [%s:%s %s]",
            event_type,
            proj,
            file_name,
            host,
            port,
            reason)

        if exception:
            self._log_to_file(event_type, proj, file, host, port, exception)

    def _log_to_file(self, event_type, proj, file, host, port, exception):
        pass

    def _success_logs(self, url: str, file: str, event_type: str):

        host, port = self._separate_url(url)
        # time - [event-type] - [fail] - [file] - [host:port]

        proj, file_name = file.split("/")[-2:]

        logger.info(
            "%s - %s's %s transmitted to [%s:%s]",
            event_type,
            proj,
            file,
            host,
            port)

    @staticmethod
    def _separate_url(host):
        separated_url = url_regex.match(host)
        host, port = separated_url.group(2, 3)
        return host, port

    event_response = {member.value: member.phrase  # type: ignore
                      for member in EventSentinel.__members__.values()}