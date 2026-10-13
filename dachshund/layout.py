from dataclasses import dataclass, field

DEFAULT_PAGE = "default"


@dataclass
class Page:
    """A named page of the dashboard, its rows in display order.

    Each row is a list of widget names, left to right. Not meant to be
    built directly, see `Dashboard.page()`/`Dashboard.row()`.
    """

    name: str
    title: str | None = None
    rows: list[list[str]] = field(default_factory=list)
