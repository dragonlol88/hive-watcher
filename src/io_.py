import typing as t
from .wrapper.stream import get_file_io
from .wrapper.stream import AsyncJson


class JsonIO:

    def __init__(self, path: str):
        self.path = path

    async def dump_to_json(self, data: t.Dict[str, t.Any]) -> None:
        """

        :param data:
        :return:
        """
        json = AsyncJson()
        async with get_file_io(self.path, 'w') as af:
            await json.dump(data, af)

    async def load_to_json(self) -> t.Dict[str, t.Dict[str, t.Any]]:
        """
        Load data from json file.
        :return:
            Dictionary object. key is project.
        """
        json = AsyncJson()
        try:
            async with get_file_io(self.path, 'r') as af:
                data = await json.load(af)
        except FileNotFoundError:
            data = {}
        return data


class FileIO(JsonIO):

    def __init__(self, path: str, files: t.Dict[str, t.Any]):
        super().__init__(path)
        self.files = files

    async def write(self):
        await self.dump_to_json(self.files)

    async def read(self):
        data = await self.load_to_json()
        self.files.update(data)