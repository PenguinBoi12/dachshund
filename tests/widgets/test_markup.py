from dachshund.widgets.markup import render_markdown


def test_render_markdown_with_headings_and_emphasis__expect_them_rendered() -> None:
    assert render_markdown("# Title\n\n**bold** and *em*") == (
        "<h1>Title</h1>\n<p><strong>bold</strong> and <em>em</em></p>\n"
    )


def test_render_markdown_with_a_list__expect_it_rendered() -> None:
    assert (
        render_markdown("- one\n- two") == "<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n"
    )


def test_render_markdown_with_raw_html__expect_it_escaped() -> None:
    assert render_markdown("<script>alert(1)</script>") == (
        "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n"
    )


def test_render_markdown_with_a_safe_link__expect_it_kept() -> None:
    html = render_markdown("[docs](https://example.com)")

    assert 'href="https://example.com"' in html
    assert ">docs<" in html


def test_render_markdown_with_a_javascript_link__expect_it_dropped() -> None:
    html = render_markdown("[danger](javascript:alert(1))")

    assert "<a" not in html


def test_render_markdown_with_a_mailto_link__expect_it_kept() -> None:
    assert 'href="mailto:a@b.com"' in render_markdown("[me](mailto:a@b.com)")
