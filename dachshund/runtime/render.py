from datetime import UTC, datetime
from typing import Any

from dachshund.registry import Dashboard
from dachshund.storage.events import DEFAULT_LIMIT
from dachshund.widgets.base import Widget
from dachshund.widgets.window import boundaries, since


async def payload(dashboard: Dashboard, widget: Widget) -> dict[str, Any]:
    """What the browser draws for a non-paginated `widget`, from what's stored."""
    window = widget.window()

    if window is None:
        events = await dashboard.events.events(
            widget.source, rollups=widget.rollup_safe, limit=widget.raw_events()
        )
        return widget.render(events)

    now = datetime.now(tz=UTC)
    zone = dashboard.timezone
    edges = boundaries(
        since(window.over, now, zone),
        now.timestamp(),
        window.every,
        zone,
        DEFAULT_LIMIT,
    )
    buckets = {
        field: await dashboard.events.summarize(
            widget.source,
            field,
            boundaries=edges,
            distinct=window.aggregate == "distinct",
        )
        for field in window.fields
    }

    return widget.render_buckets(buckets)
