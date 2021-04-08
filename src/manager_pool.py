import asyncio

from .io_ import JsonIO
from .common import UniqueList

class PoolContainer(dict):
    pass


class ManagerPool(object):

    def __init__(self,
                 loop,
                 manager_class,
                 manager_store_path):

        self.loop = loop
        self.managers = PoolContainer()
        self.manager_class = manager_class
        self.json = JsonIO(manager_store_path)

    def get_manager(self, symbol):
        proj = symbol.proj
        try:
            manager = self.managers.get(proj)
        except KeyError:
            manager = self._create_manager(symbol)
        return manager

    def _create_manager(self, symbol):
        loop = self.loop
        proj = symbol.proj
        if loop is None:
            loop = asyncio.get_event_loop()
        manager = self.manager_class(symbol.proj, loop)
        self.managers[proj] = manager
        return manager

    @property
    def num_of_manager(self):
        return len(self.managers)

    @property
    def projects(self):
        return tuple(self.managers)

    def verbose(self):
        pass

    async def write(self):
        data = {}
        for _, manager in self.managers.items():
            data.update(manager.shape)
        await self.json.dump_to_json(data)

    async def read(self):
        loop = self.loop
        data = await self.json.load_to_json()
        for proj, datum in data.items():
            manager = self.manager_class(proj, loop)
            for key, data in datum.items():
                if isinstance(data, list):
                    data = UniqueList(data)
                setattr(manager, key, data)
            self.managers[proj] = manager
