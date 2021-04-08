import os
import time
import queue
import shutil
import pytest

from src.common import EventStatus
from . import run_test_emitter, run_test_server


watcher = None
client  = None
STORED_DIR = './watcher_directory'


@pytest.fixture
def run_watcher(root_dir, ignore_pattern, proj_depth, host, port):
    return run_test_emitter(root_dir, ignore_pattern, proj_depth, host, port)


def get_client(client_address, watcher_address):
    return run_test_server(client_address, watcher_address)


def get_entries(stored_dir):
    entries = []
    for entry in os.scandir(stored_dir):
        entries.append(entry)
    return entries


def pair_of_origins(entries, origin_text):
    pair_of_origins = []

    for entry in entries:
        with open(entry.path, 'r') as f:
            keywords = [line.strip() for line in f.readlines()]
            pair_of_origins.append((origin_text[os.path.basename(entry.path)],
                                    keywords))
    return pair_of_origins


def test_file_created(run_watcher, event_num):
    global watcher

    watcher = run_watcher
    timeout = 2

    events = []
    while True:
        try:
            event = watcher.get_event(timeout)
            events.append(event)
        except queue.Empty:
            break

    assert event_num == len(events)

    for i in range(event_num):
        event = events[i]
        symbol = event.symbol
        assert symbol.event_type == EventStatus.FILE_CREATED


def test_channel_created(
        client_address, watcher_address,stored_directory, event_num
):
    global watcher
    global client
    sleep_time = 2
    client = get_client(client_address, watcher_address)
    time.sleep(sleep_time)
    entries = get_entries(stored_directory)
    event = watcher.get_event()
    watch = event.watch
    channel = watch.channels.pop()
    assert channel.split("/")[-1] == ':'.join([str(addr) for addr in client_address])
    assert len(entries) == event_num


def test_created_files(stored_directory, origin_text):

    entries = get_entries(stored_directory)
    pairs = pair_of_origins(entries, origin_text)

    for origin, keywords in pairs:
        assert origin == keywords
    shutil.rmtree(stored_directory)


def test_deleted_channel():
    global watcher
    global client

    client.close()
    event = watcher.get_event()
    watch = event.watch
    symbol = event.symbol
    assert not watch.channels
    assert symbol.event_type == EventStatus.DELETE_CHANNEL


def test_close_watcher():
    global watcher
    watcher.close()