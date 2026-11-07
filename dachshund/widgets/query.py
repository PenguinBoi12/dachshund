from dataclasses import dataclass


@dataclass(frozen=True)
class TableQuery:
    """What a table asks of its rows: a search, a sort and a page.

    ## Options

    - `search` (`str`) - Text typed in the search box. Defaults to `None`.
    - `sort_by` (`str`) - The column sorted by. Defaults to `None`, unsorted.
    - `descending` (`bool`) - Sorts highest first. Defaults to `False`.
    - `offset` (`int`) - Rows skipped before the page. Defaults to `0`.
    - `limit` (`int`) - Rows in the page. Defaults to `None`, the table's
      `page_size`.
    - `levels` (`frozenset[int]`) - The log levels a `Logs` widget shows.
      Defaults to empty, every level it captures.
    """

    search: str | None = None
    sort_by: str | None = None
    descending: bool = False
    offset: int = 0
    limit: int | None = None
    levels: frozenset[int] = frozenset()
