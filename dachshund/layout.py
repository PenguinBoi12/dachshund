from dataclasses import dataclass
from typing import Any, Callable, Iterable

from dachshund.actions import Action, make_action
from dachshund.widgets.base import Widget

DEFAULT_PAGE = "default"


@dataclass
class Column:
    """Widgets stacked top to bottom, taking one slot of a row."""

    names: list[str]


@dataclass
class Row:
    """Widgets and columns side by side, left to right.

    ## Options

    - `items` (`list[str | Column]`) - Widget names and columns, in order.
    - `widths` (`tuple[int, ...]`) - Each item's share of the row, `(2, 1)` for
      two thirds then one third. Defaults to `None`, equal shares.
    """

    items: list[str | Column]
    widths: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.widths is None:
            return

        if len(self.widths) != len(self.items):
            raise ValueError(
                f"widths has {len(self.widths)} values for "
                f"{len(self.items)} items in the row."
            )

        if any(width < 1 for width in self.widths):
            raise ValueError("Every width must be at least 1.")

    def weight(self, index: int) -> int:
        """The share of the row the item at `index` takes."""
        return self.widths[index] if self.widths else 1


def names_of(items: Iterable[Widget | str]) -> list[str]:
    """Widget names, from widgets or names."""
    return [item if isinstance(item, str) else item.name for item in items]


def row_names(row: Row) -> list[str]:
    """Every widget name in `row`, columns flattened."""
    return [
        name
        for item in row.items
        for name in (item.names if isinstance(item, Column) else [item])
    ]


def build_row(
    items: Iterable[Widget | str | Column],
    widths: Iterable[int] | None,
    take: Callable[[Widget | str], str],
) -> Row:
    """A row from widgets, names and columns, `take` naming each widget."""
    items = list(items)
    checked = Row(["" for _ in items], tuple(widths) if widths is not None else None)

    return Row(
        [item if isinstance(item, Column) else take(item) for item in items],
        checked.widths,
    )


def unplace(rows: list[Row], names: Iterable[str]) -> None:
    """Remove `names` from `rows`, dropping columns and rows left empty."""
    gone = set(names)

    for row in list(rows):
        kept: list[str | Column] = []
        weights: list[int] = []

        for index, item in enumerate(row.items):
            if isinstance(item, Column):
                item = Column([name for name in item.names if name not in gone])
                keep = bool(item.names)
            else:
                keep = item not in gone

            if keep:
                kept.append(item)
                weights.append(row.weight(index))

        if not kept:
            rows.remove(row)
        else:
            row.items = kept
            row.widths = tuple(weights) if row.widths else None


class Page:
    """A page of the dashboard, with its widgets, layout and actions.

    Register on a page, then put it on the dashboard with `dachshund.include()`.
    See the [Pages](../guides/pages.md) guide.

    ## Example

    ```python
    page = Page("overview", title="Overview")

    page.row(Text("summary"))
    page.row(
        TimeSeriesChart("latency"),
        page.column(Number("errors"), Number("users")),
        widths=(2, 1),
    )

    @page.action("flush", label="Flush cache")
    def flush(ctx): ...

    dachshund.include(page)
    ```

    ## Options

    - `name` (`str`) - The page's URL, `/<name>`. Can't contain `/`. Required.
    - `title` (`str`) - Shown in the navigation. Defaults to `name`,
      underscores as spaces.

    ## Layout

    - `row()` puts widgets side by side, equally unless given `widths`. A row
      with one widget takes the full width.
    - `column()` stacks widgets top to bottom, in one slot of a row.

    Rows show in the order they were made. `row()` and `column()` take new
    widgets, or ones already on the page, which move out of their old row.

    ## Tabs

    A page holds either widgets or `tab()`s. Its tabs are listed in a sidebar,
    and visiting the page shows the first one.
    """

    def __init__(self, name: str, *, title: str | None = None) -> None:
        if not name.strip() or "/" in name:
            raise ValueError("A page name cannot be blank or contain '/'.")

        self.name = name
        self.title = title
        self.parent: Page | None = None
        self.rows: list[Row] = []
        self.widgets: dict[str, Widget] = {}
        self.actions: dict[str, Action] = {}
        self.tabs: dict[str, Page] = {}
        self.included = False

    @property
    def path(self) -> str:
        """Where the page lives, `"parent/tab"` for a tab."""
        return f"{self.parent.path}/{self.name}" if self.parent else self.name

    def column(self, *widgets: Widget | str) -> Column:
        """Stack widgets top to bottom, for use in a `row()`."""
        return Column([self._take(widget) for widget in widgets])

    def row(
        self, *items: Widget | str | Column, widths: Iterable[int] | None = None
    ) -> None:
        """Lay widgets of this page out side by side, in a row of their own.

        ## Options

        - `widths` (`tuple[int, ...]`) - Each item's share of the row, see
          [Row][dachshund.Row]. Defaults to equal shares.
        """
        self._check_open()

        row = build_row(items, widths, self._take)
        unplace(self.rows, row_names(row))
        self.rows.append(row)

    def tab(self, name: str, *, title: str | None = None) -> "Page":
        """Add a tab, a page nested under this one, and return it.

        ## Options

        - `name` (`str`) - The tab's URL, `/<page>/<name>`. Required.
        - `title` (`str`) - Shown in the sidebar. Defaults to `name`, underscores
          as spaces.
        """
        self._check_open()

        if self.widgets:
            raise ValueError(
                f"Page {self.path!r} has widgets, it can't also have tabs."
            )

        if name in self.tabs:
            raise ValueError(f"A tab named {name!r} already exists.")

        tab = self.tabs[name] = Page(name, title=title)
        tab.parent = self

        return tab

    def action(
        self, name: str, *, label: str | None = None, confirm: bool = False
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an action, see [Dashboard.action][dachshund.Dashboard.action]."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._check_open()

            if name in self.actions:
                raise ValueError(f"An action named {name!r} already exists.")

            self.actions[name] = make_action(
                name, handler, label=label, confirm=confirm
            )
            return handler

        return decorator

    def every(self) -> list["Page"]:
        """This page and its tabs, recursively."""
        return [self, *(page for tab in self.tabs.values() for page in tab.every())]

    def _register(self, widget: Widget) -> None:
        self._check_open()

        if self.tabs:
            raise ValueError(f"Page {self.path!r} has tabs, put widgets on one.")

        if widget.name in self.widgets:
            raise ValueError(f"A widget named {widget.name!r} already exists.")

        self.widgets[widget.name] = widget

    def _take(self, item: Widget | str) -> str:
        """The name of `item`, registering it if it's a widget new to the page."""
        if isinstance(item, Widget):
            if self.widgets.get(item.name) is not item:
                self._register(item)

            return item.name

        if item not in self.widgets:
            raise ValueError(f"Not on page {self.path!r}: {item}.")

        return item

    def _check_open(self) -> None:
        if self.included:
            raise RuntimeError(
                f"Page {self.path!r} is already included in a dashboard."
            )
