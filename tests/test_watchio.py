import os
import asyncio
import pytest

from watcher.common import WatchIO
from watcher.hivewatcher import Watch

loop = asyncio.get_event_loop()

@pytest.fixture
def watches():


    watch1 = Watch('project1', loop)
    watch1.add_path("test1_ver1.txt")
    watch1.add_path("test1_ver2.txt")
    watch1.add_channel("http://192,168.0.230:5550")
    watch1.add_channel("http://192,168.0.231:5551")

    watch2 = Watch('project2', loop)
    watch2.add_path("test1_ver1.txt")
    watch2.add_path("test1_ver2.txt")
    watch2.add_channel("http://192,168.0.232:5550")
    watch2.add_channel("http://192,168.0.233:5551")

    watches = {"project1": watch1, "project2": watch2}
    return watches

@pytest.fixture
def watch_path():
    return "./watch.json"


async def record(watch_path, watches):
    wio = WatchIO(watch_path, watches)
    await wio.record()

async def load(watch_path, watch_cls):
    watches = {}
    wio = WatchIO(watch_path, watches)
    await wio.load(watch_cls, loop)
    return wio.watches

def test_watchio_record(
        watches, watch_path
):

    data = None

    async def main():
        nonlocal data
        await record(watch_path, watches)
        data = await load(watch_path, Watch)

    asyncio.run(main())
    os.remove(watch_path)
    assert data['project1'].key == watches['project1'].key
    assert data['project1'].paths == watches['project1'].paths
    assert data['project1'].channels == watches['project1'].channels

    assert data['project2'].key == watches['project2'].key
    assert data['project2'].paths == watches['project2'].paths
    assert data['project2'].channels == watches['project2'].channels
