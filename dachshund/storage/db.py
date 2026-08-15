import sqlite3
from typing import Sequence


def connect(path: str) -> sqlite3.Connection:
    """Open a WAL-mode connection to a SQLite file.

    Knows nothing about any particular schema; call `migrate()` with
    whatever tables the caller owns.

    ## Example

    ```python
    connection = connect("dachshund.db")
    migrate(connection, events.MIGRATIONS)
    ```
    """
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")

    return connection


def migrate(connection: sqlite3.Connection, migrations: Sequence[str]) -> None:
    """Bring a connection's schema up to date, one script per `user_version`.

    Idempotent: a connection already at the latest version applies nothing.

    ## Example

    ```python
    migrate(connection, ["CREATE TABLE events (...)"])
    ```
    """
    (version,) = connection.execute("PRAGMA user_version").fetchone()

    for script in migrations[version:]:
        connection.executescript(script)

    connection.execute(f"PRAGMA user_version = {len(migrations)}")
