from dachshund.layout import Page


def test_page__expect_no_title_and_no_rows_by_default() -> None:
    page = Page("requests")

    assert (page.name, page.title, page.rows) == ("requests", None, [])


def test_two_pages__expect_independent_rows() -> None:
    first = Page("requests")
    second = Page("errors")

    first.rows.append(["latency"])

    assert first.rows == [["latency"]]
    assert second.rows == []
