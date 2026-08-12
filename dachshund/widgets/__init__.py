from typing import Any

from dachshund.widgets.base import Widget
from dachshund.widgets.builtin.line import LineGraph

TYPES: dict[str, type[Widget]] = {
    LineGraph.type: LineGraph,
}

CHARTS: dict[str, type[Widget]] = {
    "line": LineGraph,
}


def build(name: str, *, type: str = "line", **options: Any) -> Widget:
    """Build a widget of a registered type.

    The source defaults to the widget's own name, so emitting under that name
    is enough to feed it.

    ## Example

    ```python
    build("latency", type="line", size=2)
    ```
    """
    if type not in TYPES:
        known = ", ".join(sorted(TYPES))
        raise ValueError(f"There is no {type!r} widget type. Known types: {known}.")

    options.setdefault("source", name)

    return TYPES[type](name=name, **options)


__all__ = [
    "CHARTS",
    "TYPES",
    "LineGraph",
    "Widget",
    "build",
]
