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


def test_row__expect_the_widget_registered() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")

    page.row(latency)

    assert page.widgets == {"latency": latency}


def test_row_of_a_duplicate_name__expect_value_error() -> None:
    page = Page("requests")
    page.row(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already exists"):
        page.row(TimeSeriesChart("latency"))


def test_row_of_widgets_and_names__expect_names_recorded() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")
    page.row(latency)
    page.row(TimeSeriesChart("errors"))

    page.row(latency, "errors")

    assert page.rows == [Row(["latency", "errors"])]


def test_row_with_a_column__expect_it_kept_as_one_slot() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")
    page.row(latency)
    errors = TimeSeriesChart("errors")
    page.row(errors)
    cpu = TimeSeriesChart("cpu")
    page.row(cpu)

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
    page.row(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="can't also have tabs"):
        page.tab("commands")


def test_row_on_a_page_with_tabs__expect_value_error() -> None:
    page = Page("activity")
    page.tab("commands")

    with pytest.raises(ValueError, match="has tabs"):
        page.row(TimeSeriesChart("latency"))


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
        page.row(TimeSeriesChart("latency"))


def test_row_with_widths__expect_them_kept() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")
    page.row(latency)
    errors = TimeSeriesChart("errors")
    page.row(errors)

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


def test_row_of_one_widget__expect_a_full_width_row_each() -> None:
    page = Page("requests")
    page.row(TimeSeriesChart("latency"))
    page.row(TimeSeriesChart("errors"))

    assert page.rows == [Row(["latency"]), Row(["errors"])]


def test_row_of_new_widgets__expect_them_added_and_placed() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")

    page.row(latency, TimeSeriesChart("errors"), widths=(2, 1))

    assert page.widgets["latency"] is latency
    assert page.rows == [Row(["latency", "errors"], (2, 1))]


def test_row_of_an_added_widget__expect_it_moved_out_of_its_row() -> None:
    page = Page("requests")
    latency = TimeSeriesChart("latency")
    page.row(latency)
    page.row(TimeSeriesChart("errors"))

    page.row(TimeSeriesChart("cpu"), latency)

    assert page.rows == [Row(["errors"]), Row(["cpu", "latency"])]


def test_row_taking_the_last_widget_of_a_column__expect_the_column_dropped() -> None:
    page = Page("requests")
    errors = TimeSeriesChart("errors")
    page.row(TimeSeriesChart("latency"), page.column(errors), widths=(2, 1))

    page.row(errors)

    assert page.rows == [Row(["latency"], (2,)), Row(["errors"])]


def test_row_of_another_widget_with_a_taken_name__expect_value_error() -> None:
    page = Page("requests")
    page.row(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already exists"):
        page.row(TimeSeriesChart("latency"))


def test_row_with_mismatched_widths__expect_nothing_added() -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="widths has 1 values for 2 items"):
        page.row(TimeSeriesChart("latency"), TimeSeriesChart("errors"), widths=(2,))

    assert page.widgets == {}
