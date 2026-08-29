from markdown_it import MarkdownIt

import nh3

_ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "strong",
    "em",
    "code",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
}

_ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}

_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}

_md = MarkdownIt("commonmark", {"html": False})


def render_markdown(content: str) -> str:
    """Render markdown source to sanitized HTML.

    Raw HTML in the source is escaped, and the output is filtered against
    an explicit tag/attribute allowlist and URL-scheme list, so e.g.
    `[x](javascript:...)`-style links are dropped.

    ## Example

    ```python
    render_markdown("**bold** and a [link](https://example.com)")
    # '<p><strong>bold</strong> and a <a href="https://example.com" rel="noopener noreferrer">link</a></p>'
    ```
    """
    html = _md.render(content)
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_ALLOWED_URL_SCHEMES,
    )
