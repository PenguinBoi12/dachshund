import threading
from typing import Any

import pytest

from dachshund.storage.protocol import SyncStorage


class DictStorage(SyncStorage):
    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    def _save(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = value

    def _load(self, key: str) -> dict[str, Any] | None:
        return self.data.get(key)


@pytest.mark.asyncio
async def test_save_then_load__expect_the_value_round_tripped() -> None:
    storage = DictStorage()

    await storage.save("commands", {"totals": {"/ban": 3}})

    assert await storage.load("commands") == {"totals": {"/ban": 3}}


@pytest.mark.asyncio
async def test_load_of_an_unknown_key__expect_none() -> None:
    assert await DictStorage().load("nothing") is None


@pytest.mark.asyncio
async def test_save_and_load__expect_them_run_off_the_calling_thread() -> None:
    class ThreadRecordingStorage(SyncStorage):
        def __init__(self) -> None:
            self.threads: set[int] = set()

        def _save(self, key: str, value: dict[str, Any]) -> None:
            self.threads.add(threading.get_ident())

        def _load(self, key: str) -> dict[str, Any] | None:
            self.threads.add(threading.get_ident())
            return None

    storage = ThreadRecordingStorage()

    await storage.save("key", {})
    await storage.load("key")

    assert threading.get_ident() not in storage.threads


@pytest.mark.asyncio
async def test_unimplemented_subclass__expect_not_implemented() -> None:
    class BareStorage(SyncStorage):
        pass

    storage = BareStorage()

    with pytest.raises(NotImplementedError):
        await storage.save("key", {})

    with pytest.raises(NotImplementedError):
        await storage.load("key")
