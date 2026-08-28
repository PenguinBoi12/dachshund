import sqlite3
from pathlib import Path

import pytest

from dachshund.storage import db


def test_connect__expect_wal_journal_mode(tmp_path: Path) -> None:
    connection = db.connect(str(tmp_path / "test.db"))

    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_migrate__expect_the_scripts_applied_in_order(tmp_path: Path) -> None:
    connection = db.connect(str(tmp_path / "test.db"))

    db.migrate(
        connection, ["CREATE TABLE a (id INTEGER)", "CREATE TABLE b (id INTEGER)"]
    )

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert {"a", "b"} <= tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_setup__expect_a_migrated_wal_connection(tmp_path: Path) -> None:
    connection, executor = db.setup(
        str(tmp_path / "test.db"), ["CREATE TABLE a (id INTEGER)"]
    )

    def query(sql: str) -> list:
        # The connection was opened on the executor's own thread; every
        # later touch has to go through it too, same as production code.
        return connection.execute(sql).fetchall()

    try:
        assert executor.submit(query, "PRAGMA journal_mode").result()[0][0] == "wal"
        assert executor.submit(query, "PRAGMA user_version").result()[0][0] == 1

        tables = {
            row[0]
            for row in executor.submit(
                query, "SELECT name FROM sqlite_master WHERE type='table'"
            ).result()
        }
        assert "a" in tables
    finally:
        executor.shutdown()


def test_setup_without_migrations__expect_the_version_untouched(tmp_path: Path) -> None:
    connection, executor = db.setup(str(tmp_path / "test.db"))

    try:
        version = executor.submit(
            lambda: connection.execute("PRAGMA user_version").fetchone()[0]
        ).result()
        assert version == 0
    finally:
        executor.shutdown()


def test_close__expect_the_connection_and_executor_stopped(tmp_path: Path) -> None:
    connection, executor = db.setup(str(tmp_path / "test.db"))

    db.close(connection, executor)

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    with pytest.raises(RuntimeError):
        executor.submit(lambda: None)


def test_migrate_of_an_up_to_date_connection__expect_nothing_reapplied(
    tmp_path: Path,
) -> None:
    connection = db.connect(str(tmp_path / "test.db"))
    migrations = ["CREATE TABLE a (id INTEGER)"]

    db.migrate(connection, migrations)
    db.migrate(connection, migrations)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migrate_with_a_new_script__expect_only_it_applied(tmp_path: Path) -> None:
    connection = db.connect(str(tmp_path / "test.db"))

    db.migrate(connection, ["CREATE TABLE a (id INTEGER)"])
    db.migrate(
        connection, ["CREATE TABLE a (id INTEGER)", "CREATE TABLE b (id INTEGER)"]
    )

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert {"a", "b"} <= tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_migrate_with_a_failing_script__expect_earlier_scripts_kept(
    tmp_path: Path,
) -> None:
    connection = db.connect(str(tmp_path / "test.db"))
    migrations = ["CREATE TABLE a (id INTEGER)", "NOT VALID SQL"]

    with pytest.raises(sqlite3.OperationalError):
        db.migrate(connection, migrations)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1

    db.migrate(
        connection, ["CREATE TABLE a (id INTEGER)", "CREATE TABLE b (id INTEGER)"]
    )

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert {"a", "b"} <= tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
