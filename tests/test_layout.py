import pytest

from dachshund.layout import Column, Page, Row
from dachshund.widgets.chart.timeseries import TimeSeriesChart


def chart(name: str) -> TimeSeriesChart:
    return TimeSeriesChart(name)


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

    with first.row():
        first.add(chart("latency"))

    assert first.rows == [Row([Column(["latency"])])]
    assert second.rows == []


def test_add_outside_a_row__expect_value_error_and_nothing_registered() -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="add\\(\\) goes inside a row"):
        page.add(chart("latency"))

    assert (page.rows, page.widgets) == ([], {})


def test_one_widget_rows__expect_a_full_width_row_each() -> None:
    page = Page("requests")
    latency = chart("latency")

    with page.row():
        page.add(latency)
    with page.row():
        page.add(chart("errors"))

    assert page.widgets["latency"] is latency
    assert page.rows == [Row([Column(["latency"])]), Row([Column(["errors"])])]
    assert page.rows[0].spans() == [12]


def test_add_inside_a_tab_but_outside_a_row__expect_value_error() -> None:
    page = Page("activity")

    with pytest.raises(ValueError, match="goes inside a row"):
        with page.tab("commands"):
            page.add(chart("calls"))


def test_add_in_a_row__expect_a_column_each() -> None:
    page = Page("requests")

    with page.row():
        page.add(chart("latency"))
        page.add(chart("errors"))

    assert page.rows == [Row([Column(["latency"]), Column(["errors"])])]


def test_add_in_a_col__expect_the_widgets_stacked() -> None:
    page = Page("requests")

    with page.row():
        with page.column(span=4):
            page.add(chart("errors"))
            page.add(chart("users"))
        page.add(chart("latency"))

    assert page.rows == [Row([Column(["errors", "users"], 4), Column(["latency"])])]


def test_add_in_a_loop__expect_every_widget_placed() -> None:
    page = Page("requests")

    with page.row():
        for name in ("a", "b", "c"):
            page.add(chart(name))

    assert page.rows[0].spans() == [4, 4, 4]


@pytest.mark.parametrize(
    "spans, expected",
    [
        ([None], [12]),
        ([None, None], [6, 6]),
        ([None, None, None], [4, 4, 4]),
        ([None] * 5, [3, 3, 2, 2, 2]),
        ([3, None], [3, 9]),
        ([4, 8], [4, 8]),
        ([None, 6, None], [3, 6, 3]),
    ],
)
def test_row_spans__expect_unsized_columns_sharing_what_is_left(
    spans: list[int | None], expected: list[int]
) -> None:
    assert Row([Column([], span) for span in spans]).spans() == expected


def test_row_spanning_past_twelve__expect_nothing_added() -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="span 13 columns"):
        with page.row():
            with page.column(span=8):
                page.add(chart("latency"))
            with page.column(span=5):
                page.add(chart("errors"))

    assert (page.rows, page.widgets) == ([], {})


@pytest.mark.parametrize("span", [0, 13])
def test_col_with_a_span_off_the_grid__expect_value_error(span: int) -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="between 1 and 12"):
        with page.row():
            with page.column(span=span):
                pass


def test_col_outside_a_row__expect_value_error() -> None:
    with pytest.raises(ValueError, match="directly inside a row"):
        with Page("requests").column():
            pass


def test_row_inside_a_row__expect_value_error() -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="inside another row"):
        with page.row():
            with page.row():
                pass


def test_error_inside_a_row__expect_no_row_and_the_page_usable() -> None:
    page = Page("requests")

    with pytest.raises(RuntimeError, match="boom"):
        with page.row():
            page.add(chart("latency"))
            raise RuntimeError("boom")

    with page.row():
        page.add(chart("latency"))

    assert page.rows == [Row([Column(["latency"])])]


def test_duplicate_name_in_a_row__expect_nothing_registered() -> None:
    page = Page("requests")

    with pytest.raises(ValueError, match="already exists"):
        with page.row():
            page.add(chart("latency"))
            page.add(chart("latency"))

    assert (page.rows, page.widgets) == ([], {})


def test_add_of_a_duplicate_name__expect_value_error() -> None:
    page = Page("requests")
    with page.row():
        page.add(chart("latency"))

    with pytest.raises(ValueError, match="already exists"):
        with page.row():
            page.add(chart("latency"))


def test_tab__expect_rows_and_widgets_on_a_nested_page() -> None:
    page = Page("activity")

    with page.tab("commands", title="Commands") as tab:
        with page.row():
            page.add(chart("calls"))
            page.add(chart("errors"))

    assert page.tabs == {"commands": tab}
    assert (tab.parent, tab.path, tab.title) == (page, "activity/commands", "Commands")
    assert tab.rows == [Row([Column(["calls"]), Column(["errors"])])]
    assert page.rows == []
    assert page.every() == [page, tab]


def test_tab_inside_a_row__expect_value_error() -> None:
    page = Page("activity")

    with pytest.raises(ValueError, match="tab can't be opened inside a row"):
        with page.row():
            with page.tab("commands"):
                pass


def test_tab_on_a_page_with_widgets__expect_value_error() -> None:
    page = Page("activity")
    with page.row():
        page.add(chart("latency"))

    with pytest.raises(ValueError, match="can't also have tabs"):
        with page.tab("commands"):
            pass


def test_add_on_a_page_with_tabs__expect_value_error() -> None:
    page = Page("activity")

    with page.tab("commands"):
        pass

    with pytest.raises(ValueError, match="has tabs"):
        with page.row():
            page.add(chart("latency"))


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
        with page.row():
            page.add(chart("latency"))
