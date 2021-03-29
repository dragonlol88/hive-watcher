import os
import asyncio
import pytest
from watcher.wrapper.stream import AsyncJson
from watcher.wrapper.stream import get_file_io


@pytest.fixture
def watch_path():
    return './watches.json'


@pytest.fixture
def json_data():
    return {"test1": 'hello world', 'test2': 'hello watcher'}


async def write(path, data, mode):
    json = AsyncJson()
    async with get_file_io(path, mode) as f:
        await json.dump(data, f)


async def load(path, mode):
    json = AsyncJson()
    async with get_file_io(path, mode) as f:
        data = await json.load(f)
    return data


def test_async_json_dump_as_obj(
        watch_path, json_data
):
    data = None

    async def main():
        nonlocal data
        await write(watch_path, json_data, 'w')
        data = await load(watch_path, 'r')

    asyncio.run(main())
    os.remove(watch_path)
    assert data == json_data

