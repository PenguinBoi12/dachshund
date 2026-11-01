import pytest

from dachshund.layout import Column, Page, Row
from dachshund.widgets.chart.timeseries import TimeSeriesChart


def test_page__expect_no_title_and_no_rows_by_default() -> None:
    page = Page("requests")

    assert (page.name, page.title, page.rows) == ("requests", None, [])


@pytest.mark.parametrize("name", ["", "  ", "a/b"])
def test_page_with_a_bad_name__expect_value_error(name: str) -> None:
    with pytest.raises(ValueError, match="blank or contain '/'"):
        Page(name)


def test_two_pages__expect_independent_rows() -> None:
    first = Page("requests")
    second = Page("errors")

    first.rows.append(Row(["latency"]))

    assert first.rows == [Row(["latency"])]
    assert second.rows == []


def test_add__expect_the_widget_returned() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")

    assert page.add(latency) is latency
    assert page.widgets == {"latency": latency}


def test_add_a_duplicate_name__expect_value_error() -> None:
    page = Page("requests")
    page.add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already exists"):
        page.add(TimeSeriesChart("latency"))


def test_row_of_widgets_and_names__expect_names_recorded() -> None:
    page = Page("requests")
    latency = page.add(TimeSeriesChart("latency"))
    page.add(TimeSeriesChart("errors"))

    page.row(latency, "errors")

    assert page.rows == [Row(["latency", "errors"])]


def test_row_with_a_column__expect_it_kept_as_one_slot() -> None:
    page = Page("requests")
    latency = page.add(TimeSeriesChart("latency"))
    errors = page.add(TimeSeriesChart("errors"))
    cpu = page.add(TimeSeriesChart("cpu"))

    page.row(latency, page.column(errors, cpu))

    assert page.rows == [Row(["latency", Column(["errors", "cpu"])])]


@pytest.mark.parametrize("call", ["row", "column"])
def test_row_or_column_of_a_widget_not_on_the_page__expect_value_error(
    call: str,
) -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="Not on page 'requests': ghost"):
        getattr(page, call)("ghost")


def test_tab__expect_a_nested_page_with_a_path() -> None:
    page = Page("activity")
    tab = page.tab("commands", title="Commands")

    assert page.tabs == {"commands": tab}
    assert (tab.parent, tab.path, tab.title) == (page, "activity/commands", "Commands")
    assert page.every() == [page, tab]


def test_tab_on_a_page_with_widgets__expect_value_error() -> None:
    page = Page("activity")
    page.add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="can't also have tabs"):
        page.tab("commands")


def test_add_on_a_page_with_tabs__expect_value_error() -> None:
    page = Page("activity")
    page.tab("commands")

    with pytest.raises(ValueError, match="has tabs"):
        page.add(TimeSeriesChart("latency"))


def test_action__expect_it_registered_and_the_handler_returned() -> None:
    page = Page("requests")

    def flush(ctx: dict) -> None: ...

    assert page.action("flush", label="Flush")(flush) is flush
    assert page.actions["flush"].label == "Flush"


def test_action_without_ctx__expect_type_error() -> None:
    page = Page("requests")

    with pytest.raises(TypeError, match="must take `ctx`"):

        @page.action("flush")
        def flush() -> None: ...


def test_registering_on_an_included_page__expect_runtime_error() -> None:
    page = Page("requests")
    page.included = True

    with pytest.raises(RuntimeError, match="already included"):
        page.add(TimeSeriesChart("latency"))


def test_row_with_widths__expect_them_kept() -> None:
    page = Page("requests")
    latency = page.add(TimeSeriesChart("latency"))
    errors = page.add(TimeSeriesChart("errors"))

    page.row(latency, errors, widths=(2, 1))

    assert page.rows == [Row(["latency", "errors"], (2, 1))]
    assert [page.rows[0].weight(i) for i in range(2)] == [2, 1]


def test_row_without_widths__expect_equal_weights() -> None:
    assert Row(["latency", "errors"]).weight(1) == 1


def test_row_with_a_width_per_item_missing__expect_value_error() -> None:
    with pytest.raises(ValueError, match="widths has 1 values for 2 items"):
        Row(["latency", "errors"], (2,))


def test_row_with_a_zero_width__expect_value_error() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Row(["latency", "errors"], (2, 0))
