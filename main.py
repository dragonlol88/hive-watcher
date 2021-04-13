
from src.watcher import HiveWatcher
from src.config import Config
if __name__ == '__main__':

    config = Config("watcher", "sample/project")
    hw = HiveWatcher(config
                 )
    hw.watch()
