from pathlib import Path

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
