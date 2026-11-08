from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar

import pytest

from dachshund.storage.events import Bucket, Event
from dachshund.widgets import AggregatedWidget, BarChart, Number, TimeSeriesChart
from dachshund.widgets.aggregate import aggregated, merged
from dachshund.widgets.window import Window


def bucket(**fields: Any) -> Bucket:
    return Bucket(0.0, **fields)


FULL = bucket(count=4, values=3, sum=60.0, min=10.0, max=30.0, distinct={"a", "b"})


@pytest.mark.parametrize(
    "aggregate, expected",
    [
        ("count", 4),
        ("sum", 60.0),
        ("average", 20.0),
        ("min", 10.0),
        ("max", 30.0),
        ("distinct", 2),
    ],
)
def test_aggregated__expect_each_aggregate(aggregate: str, expected: float) -> None:
    assert aggregated(FULL, aggregate) == expected


@pytest.mark.parametrize("aggregate", ["sum", "average", "min", "max"])
def test_aggregated_without_numbers__expect_none(aggregate: str) -> None:
    assert aggregated(bucket(count=2), aggregate) is None


def test_aggregated_distinct_not_kept__expect_none() -> None:
    assert aggregated(bucket(count=2), "distinct") is None


def test_aggregated_of_an_unknown_aggregate__expect_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown aggregate"):
        aggregated(FULL, "median")


def test_merged__expect_one_bucket_holding_all() -> None:
    total = merged(
        [
            bucket(count=1, values=1, sum=5.0, min=5.0, max=5.0, distinct={"a"}),
            bucket(count=2, values=1, sum=0.0, min=0.0, max=0.0, distinct={"b"}),
        ]
    )

    assert (total.count, total.values, total.sum, total.min, total.max) == (
        3,
        2,
        5.0,
        0.0,
        5.0,
    )
    assert total.distinct == {"a", "b"}


def test_merged_with_an_untracked_bucket__expect_distinct_none() -> None:
    total = merged([bucket(distinct={"a"}), bucket(distinct=None)])

    assert total.distinct is None


@dataclass
class Gauge(AggregatedWidget):
    type: ClassVar[str] = "test_aggregated_gauge"

    def render_value(self, value: float | None) -> dict[str, Any]:
        return {"gauge": value}


def test_custom_aggregated_widget_last__expect_the_latest_value() -> None:
    gauge = Gauge("latency")

    assert gauge.render(
        [Event("latency", {"value": 1}), Event("latency", {"value": 7})]
    ) == {"gauge": 7.0}
    assert gauge.window() is None


def test_custom_aggregated_widget_windowed__expect_buckets_aggregated() -> None:
    gauge = Gauge("latency", y="ms", aggregate="average", over=timedelta(hours=1))

    assert gauge.window() == Window(
        fields=("ms",), aggregate="average", over=timedelta(hours=1)
    )
    assert gauge.render_buckets(
        {"ms": [FULL, bucket(count=1, values=1, sum=20.0)]}
    ) == {"gauge": 20.0}


def test_aggregated_widget_without_render_value__expect_not_implemented() -> None:
    @dataclass
    class Bare(AggregatedWidget):
        type: ClassVar[str] = "test_bare_aggregated"

    with pytest.raises(NotImplementedError, match="render_value"):
        Bare("x").render([])


@pytest.mark.parametrize(
    "options, message",
    [
        ({"aggregate": "median"}, "can't aggregate 'median'"),
        ({"over": timedelta(hours=1)}, "shows the last value"),
        ({"aggregate": "count", "over": "year"}, "use a timedelta or one of"),
        ({"aggregate": "count", "persist": True}, "only for aggregate='last'"),
    ],
)
def test_number_with_bad_options__expect_value_error(
    options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Number("requests", **options)


def test_number_windowed__expect_the_aggregate_and_its_unit() -> None:
    number = Number("latency", aggregate="max", over="day", unit="ms")

    assert number.render_buckets({"value": [FULL]}) == {"value": 30.0, "unit": "ms"}


@pytest.mark.parametrize(
    "options, message",
    [
        (
            {"aggregate": "last", "every": timedelta(minutes=1)},
            "can't aggregate 'last'",
        ),
        ({"aggregate": "count"}, "give it `every`"),
        (
            {"aggregate": "count", "every": timedelta(seconds=30)},
            "whole number of minutes",
        ),
        (
            {"aggregate": "count", "every": timedelta(seconds=90)},
            "whole number of minutes",
        ),
        ({"every": timedelta(minutes=1)}, "no aggregate"),
        (
            {"aggregate": "count", "every": timedelta(minutes=1), "over": 5},
            "use a timedelta",
        ),
    ],
)
def test_timeseries_with_bad_options__expect_value_error(
    options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TimeSeriesChart("requests", **options)


def test_timeseries_windowed__expect_a_point_per_bucket_per_field() -> None:
    chart = TimeSeriesChart(
        "latency",
        y=["check", "command"],
        aggregate="average",
        every=timedelta(minutes=1),
    )
    first = Bucket(60.0, count=2, values=2, sum=30.0)
    second = Bucket(120.0, count=1)

    payload = chart.render_buckets(
        {"check": [first, second], "command": [second, first]}
    )

    assert chart.window() == Window(
        fields=("check", "command"), aggregate="average", every=timedelta(minutes=1)
    )
    assert payload == {
        "series": ["check", "command"],
        "x": [60.0, 120.0],
        "y": [[15.0, None], [None, 15.0]],
    }


def test_bar_with_last__expect_value_error() -> None:
    with pytest.raises(ValueError, match="can't aggregate 'last'"):
        BarChart("commands", x="name", aggregate="last")


@pytest.mark.parametrize(
    "aggregate, expected",
    [
        ("count", [3, 1]),
        ("sum", [12.0, 1.0]),
        ("average", [6.0, 1.0]),
        ("min", [2.0, 1.0]),
        ("max", [10.0, 1.0]),
    ],
)
def test_bar_aggregate__expect_it_per_category(
    aggregate: str, expected: list[float]
) -> None:
    chart = BarChart("commands", x="name", y="ms", aggregate=aggregate)
    events = [
        Event("commands", {"name": "/ban", "ms": 2}),
        Event("commands", {"name": "/ban", "ms": 10}),
        Event("commands", {"name": "/ban"}),
        Event("commands", {"name": "/help", "ms": 1}),
    ]

    assert chart.render(events)["y"] == [expected]


def test_bar_distinct__expect_distinct_values_per_category() -> None:
    chart = BarChart("commands", x="name", y="user", aggregate="distinct", persist=True)

    for user in ("ada", "ada", "bob"):
        chart.accumulate(Event("commands", {"name": "/ban", "user": user}))

    assert chart.render([]) == {"series": ["user"], "x": ["/ban"], "y": [[2]]}


def test_bar_restore_of_an_old_total__expect_the_sum_exact() -> None:
    chart = BarChart("commands", x="name", persist=True)
    chart.restore({"entries": {"/ban": 4.0}, "seen_at": {}})

    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}))

    assert chart.render([])["y"] == [[5.0]]
