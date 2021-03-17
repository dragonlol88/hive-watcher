
from . import server_on

try:
    server_on()
except:
    raise Exception
#
# buffer = LocalBuffer('../../test-config', 1, '\..*')
# import time
#
# while True:
#     time.sleep(1)
#     events = buffer.read_events()
#
#     for event in events:
#         print("created: ", event.is_created)
#         print("modified: ", event.is_modified)
#         print("deleted: ", event.is_deleted)
#         print(event.proj, event.path, event.event_status)