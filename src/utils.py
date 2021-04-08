# mypy: ignore-errors
import asyncio

try:
    from asyncio import get_running_loop
except ImportError:

    def get_running_loop():
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            raise RuntimeError("no running event loop")
        return loop