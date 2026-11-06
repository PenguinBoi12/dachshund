from datetime import UTC, datetime
from typing import Any

from dachshund.registry import Dashboard
from dachshund.storage.events import DEFAULT_LIMIT
from dachshund.widgets.base import Widget
from dachshund.widgets.window import boundaries, since


def windowed(widget: Widget) -> bool:
    """Whether `widget` is built from stored buckets over a window."""
    return bool(getattr(widget, "windowed", False))


async def payload(dashboard: Dashboard, widget: Widget) -> dict[str, Any]:
    """What the browser draws for a non-paginated `widget`, from what's stored."""
    if windowed(widget):
        now = datetime.now(tz=UTC)
        zone = dashboard.timezone
        edges = boundaries(
            since(getattr(widget, "over", None), now, zone),
            now.timestamp(),
            getattr(widget, "every", None),
            zone,
            DEFAULT_LIMIT,
        )
        distinct = getattr(widget, "aggregate", None) == "distinct"
        buckets = {
            field: await dashboard.events.summarize(
                widget.source, field, boundaries=edges, distinct=distinct
            )
            for field in getattr(widget, "fields")
        }

        return widget.render_buckets(buckets)  # type: ignore[attr-defined, no-any-return]

    events = await dashboard.events.events(widget.source, rollups=widget.rollup_safe)

    return widget.render(events)
