from pathlib import Path

import pytest

from dachshund.storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path: Path) -> SQLiteStorage:
    return SQLiteStorage(str(tmp_path / "state.db"))


@pytest.mark.asyncio
async def test_save_then_load__expect_the_value_round_tripped(
    storage: SQLiteStorage,
) -> None:
    await storage.save("commands", {"totals": {"/ban": 3}})

    assert await storage.load("commands") == {"totals": {"/ban": 3}}


@pytest.mark.asyncio
async def test_load_of_an_unknown_key__expect_none(storage: SQLiteStorage) -> None:
    assert await storage.load("nothing") is None


@pytest.mark.asyncio
async def test_saving_the_same_key_twice__expect_the_new_value_kept(
    storage: SQLiteStorage,
) -> None:
    await storage.save("commands", {"totals": {"/ban": 1}})
    await storage.save("commands", {"totals": {"/ban": 2}})

    assert await storage.load("commands") == {"totals": {"/ban": 2}}


@pytest.mark.asyncio
async def test_a_second_connection_to_the_same_file__expect_the_save_kept(
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "state.db")
    storage = SQLiteStorage(path)

    await storage.save("commands", {"totals": {"/ban": 1}})

    reopened = SQLiteStorage(path)

    assert await reopened.load("commands") == {"totals": {"/ban": 1}}
