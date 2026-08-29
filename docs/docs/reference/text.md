# Text

`Text` shows the latest markdown from its source, rendered to sanitized HTML: headings, bold/italic, lists, blockquotes, code, and links.

```python
import dachshund

dachshund.widget("changelog", type="text", title="Release Notes")
dachshund.emit("changelog", value="**v1.2** fixed the thing. See [notes](https://example.com).")
```

Rendered output is sanitized (`markdown-it-py` + `nh3`): raw HTML tags in the source are escaped rather than passed through, and only `http`/`https`/`mailto` links are kept.

::: dachshund.widgets.text.text.Text
