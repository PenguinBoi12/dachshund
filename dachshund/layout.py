from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from dachshund.actions import Action, make_action
from dachshund.widgets.base import Widget

DEFAULT_PAGE = "default"
COLUMNS = 12


@dataclass
class Column:
    """Widgets stacked top to bottom in one column of a row.

    ## Options

    - `names` (`list[str]`) - The widgets, top to bottom.
    - `span` (`int`) - Columns wide, out of 12. Defaults to `None`, an even
      share of what the row's other columns leave.
    """

    names: list[str] = field(default_factory=list)
    span: int | None = None


@dataclass
class Row:
    """Columns side by side on a 12-column grid."""

    columns: list[Column] = field(default_factory=list)

    def spans(self) -> list[int]:
        """Each column's width out of 12. Unsized columns share what's left evenly."""
        fixed = sum(column.span or 0 for column in self.columns)
        free = [
            index for index, column in enumerate(self.columns) if column.span is None
        ]
        share, extra = divmod(max(COLUMNS - fixed, len(free)), len(free) or 1)

        return [
            column.span or share + (1 if free.index(index) < extra else 0)
            for index, column in enumerate(self.columns)
        ]

    def check(self) -> None:
        fixed = sum(column.span or 0 for column in self.columns)

        if fixed > COLUMNS:
            raise ValueError(
                f"The row's columns span {fixed} columns, the grid has 12."
            )


def names_of(items: Iterable[Widget | str]) -> list[str]:
    """Widget names, from widgets or names."""
    return [item if isinstance(item, str) else item.name for item in items]


def row_names(row: Row) -> list[str]:
    """Every widget name in `row`, top to bottom in each column, left to right."""
    return [name for column in row.columns for name in column.names]


Register = Callable[["Page", Widget], None]
Unregister = Callable[["Page", str], None]


class Builder:
    """The `with` blocks open on a page, and where `add()` puts a widget.

    Widgets added inside a row are registered when the row closes, all or
    none, so a row that fails leaves nothing behind.
    """

    def __init__(
        self, root: "Page", register: Register, unregister: Unregister
    ) -> None:
        self.root = root
        self.register = register
        self.unregister = unregister
        self.open: list[Page | Row | Column] = []
        self.pending: list[Widget] = []

    @contextmanager
    def row(self) -> Iterator[Row]:
        if isinstance(self._inner(), (Row, Column)):
            raise ValueError("A row can't be opened inside another row.")

        page = self._page()

        if page.tabs:
            raise ValueError(f"Page {page.path!r} has tabs, put rows on one.")

        row = Row()
        self.open.append(row)

        try:
            yield row
        finally:
            self.open.pop()
            pending, self.pending = self.pending, []

        row.check()
        self._commit(page, pending)

        if row.columns:
            page.rows.append(row)

    @contextmanager
    def column(self, span: int | None = None) -> Iterator[Column]:
        row = self._inner()

        if not isinstance(row, Row):
            raise ValueError("A column goes directly inside a row.")

        if span is not None and not 1 <= span <= COLUMNS:
            raise ValueError(f"A column's span is between 1 and {COLUMNS}.")

        column = Column(span=span)
        self.open.append(column)

        try:
            yield column
        finally:
            self.open.pop()

        row.columns.append(column)

    @contextmanager
    def tab(self, name: str, title: str | None = None) -> Iterator["Page"]:
        if isinstance(self._inner(), (Row, Column)):
            raise ValueError("A tab can't be opened inside a row.")

        tab = self._page()._new_tab(name, title)
        self.open.append(tab)

        try:
            yield tab
        finally:
            self.open.pop()

    def add(self, widget: Widget) -> None:
        inner = self._inner()

        if isinstance(inner, Column):
            inner.names.append(widget.name)
            self.pending.append(widget)
        elif isinstance(inner, Row):
            inner.columns.append(Column([widget.name]))
            self.pending.append(widget)
        else:
            raise ValueError("add() goes inside a row: with page.row(): page.add(...)")

    def _page(self) -> "Page":
        pages = [block for block in self.open if isinstance(block, Page)]
        return pages[-1] if pages else self.root

    def _inner(self) -> "Page | Row | Column | None":
        return self.open[-1] if self.open else None

    def _commit(self, page: "Page", widgets: list[Widget]) -> None:
        registered: list[str] = []

        try:
            for widget in widgets:
                self.register(page, widget)
                registered.append(widget.name)
        except Exception:
            for name in registered:
                self.unregister(page, name)
            raise


class Page:
    """A page of the dashboard, with its widgets, layout and actions.

    Register on a page, then put it on the dashboard with `dachshund.include()`.
    See the [Pages](../guides/pages.md) guide.

    ## Example

    ```python
    page = Page("overview", title="Overview")

    with page.row():
        page.add(Text("summary"))

    with page.row():
        with page.column(span=4):
            page.add(Number("errors"))
            page.add(Number("users"))
        page.add(TimeSeriesChart("latency"))


    @page.action("flush", label="Flush cache")
    def flush(ctx): ...


    dachshund.include(page)
    ```

    ## Options

    - `name` (`str`) - The page's URL, `/<name>`. Can't contain `/`. Required.
    - `title` (`str`) - Shown in the navigation. Defaults to `name`,
      underscores as spaces.
    - `public` (`bool`) - Shown without the dashboard's `authorize`, see
      [Authentication](../guides/authentication.md). Its tabs follow it.
      Defaults to `False`.

    ## Layout

    A page is rows on a 12-column grid, laid out with `with` blocks. Widgets
    live in rows: `add()` puts a widget in the innermost open block,

    - in a `column()`, stacked under the widgets already there
    - in a `row()`, as a column of its own

    and raises outside of both. A full-width widget is a row with one widget.

    A column's `span` is its width out of 12. Columns without one share what's
    left evenly.

    ## Tabs

    A page holds either widgets or `tab()`s. Its tabs are listed in a sidebar,
    and visiting the page shows the first one.
    """

    def __init__(
        self, name: str, *, title: str | None = None, public: bool = False
    ) -> None:
        if not name.strip() or "/" in name:
            raise ValueError("A page name cannot be blank or contain '/'.")

        self.name = name
        self.title = title
        self.public = public
        self.parent: Page | None = None
        self.rows: list[Row] = []
        self.widgets: dict[str, Widget] = {}
        self.actions: dict[str, Action] = {}
        self.tabs: dict[str, Page] = {}
        self.included = False
        self._builder = Builder(
            self, lambda page, widget: page._register(widget), Page._unregister
        )

    @property
    def path(self) -> str:
        """Where the page lives, `"parent/tab"` for a tab."""
        return f"{self.parent.path}/{self.name}" if self.parent else self.name

    def row(self) -> AbstractContextManager[Row]:
        """Open a row: widgets added until the block ends sit side by side.

        ## Example

        ```python
        with page.row():
            page.add(Number("errors"))
            page.add(TimeSeriesChart("latency"))
        ```
        """
        return self._builder.row()

    def column(self, *, span: int | None = None) -> AbstractContextManager[Column]:
        """Open a column inside a row: widgets added until the block ends stack.

        ## Options

        - `span` (`int`) - Columns wide, out of 12. Defaults to an even share
          of what the row's other columns leave.
        """
        return self._builder.column(span)

    def tab(
        self, name: str, *, title: str | None = None
    ) -> AbstractContextManager["Page"]:
        """Open a tab: rows and widgets added until the block ends go on it.

        A tab is a page nested under this one, at `/<page>/<name>`.

        ## Options

        - `name` (`str`) - The tab's URL. Required.
        - `title` (`str`) - Shown in the sidebar. Defaults to `name`, underscores
          as spaces.
        """
        return self._builder.tab(name, title)

    def add(self, widget: Widget) -> None:
        """Put a widget in the open row or column, see [Layout](#layout)."""
        self._builder.add(widget)

    def _new_tab(self, name: str, title: str | None) -> "Page":
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
        self,
        name: str,
        *,
        label: str | None = None,
        confirm: bool = False,
        public: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an action, see [Dashboard.action][dachshund.registry.Dashboard.action]."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._check_open()

            if name in self.actions:
                raise ValueError(f"An action named {name!r} already exists.")

            self.actions[name] = make_action(
                name, handler, label=label, confirm=confirm, public=public
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

    def _unregister(self, name: str) -> None:
        self.widgets.pop(name, None)

    def _check_open(self) -> None:
        if self.included:
            raise RuntimeError(
                f"Page {self.path!r} is already included in a dashboard."
            )
