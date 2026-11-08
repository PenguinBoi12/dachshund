# Authentication

By default, anyone who can reach the dashboard sees every page and runs every action. Give it an `authorize` function to decide who gets in, using whatever auth your application already has.

```python
def authorize(request) -> bool:
    return request.cookies.get("session") in sessions


dachshund.init("My service", host="0.0.0.0", authorize=authorize)
```

`authorize` gets the request: its `headers`, `cookies`, `remote` address and `path`. It returns whether to let it in, and can be sync or async. A sync one runs in a thread, so it can query a database. One that raises denies the request, and the error is logged.

## Public and private

Once `authorize` is set, every page and action is private: `authorize` must pass to see or run it. Mark the ones anyone can use with `public=True`:

```python
from dachshund import Page

status_page = Page("status", public=True)  # anyone
admin_page = Page("admin")  # authorize() must pass


@status_page.action("refresh", public=True)  # anyone
def refresh(ctx) -> None: ...


@status_page.action("restart")  # private, even on a public page
def restart(ctx) -> None: ...
```

- A tab follows its page.
- Actions registered with `@dachshund.action(...)` take `public=True` the same way.
- The default page, where `dachshund.add()` puts widgets without a `Page`, is made public with `dachshund.page("default", public=True)`.
- A visitor `authorize` turns down only sees the public pages in the navigation, and no button for the private actions.

## Logging in

When `authorize` turns down a private page, the browser asks for a username and password, for [HTTP Basic](#http-basic) auth. With a `login_url`, the visitor is sent to your application's login page instead, with the page they wanted as `next`:

```python
dachshund.init(
    "My service", authorize=authorize, login_url="https://myapp.example/login"
)
```

With a login page, from `login_url` or `login`, the footer shows **Log in** to a visitor `authorize` turns down, back to the page they're on. With a `"logout"` handler in `login`, it shows **Log out** to one it lets in.

Dachshund has no login page of its own: the visitor logs in to your application, which sets its session cookie, and `authorize` checks that cookie.

Browsers send a cookie to every port of the host that set it, so a cookie set by your application on `myapp.example` reaches the dashboard on `myapp.example:1212`. For a dashboard on another subdomain, the cookie needs a `Domain` covering both.

### On the dashboard itself

An application with no web server of its own, like a bot logging in with OAuth, gives the dashboard its login handlers with `login`. Each one is an async aiohttp handler, served at `/_auth/<name>` without `authorize`, and a denied page redirects to `/_auth/login`:

```python
dachshund.init(
    "My bot",
    authorize=authorize,
    login={"login": login, "callback": callback, "logout": logout},
)
```

- `"login"` is required. It gets the page the visitor wanted as `next`.
- `callback` sets the session cookie that `authorize` checks. With OAuth, the provider's redirect URI is `https://<dashboard>/_auth/callback`.
- `login` and `login_url` can't be combined: there's one place to log in.
- Without `login`, nothing is served under `/_auth/`.

## With an auth library

`authorize` checks whatever your application already uses.

### Django

```python
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore


def authorize(request) -> bool:
    session = SessionStore(request.cookies.get("sessionid"))
    user_id = session.get("_auth_user_id")

    return (
        user_id is not None
        and get_user_model().objects.filter(pk=user_id, is_staff=True).exists()
    )


dachshund.init(
    "My site", authorize=authorize, login_url="https://mysite.example/accounts/login/"
)
```

### Flask-Login

```python
from flask_login import current_user

from myapp import app


def authorize(request) -> bool:
    cookie = request.headers.get("Cookie", "")

    with app.test_request_context(headers={"Cookie": cookie}):
        return current_user.is_authenticated
```

### JWT (FastAPI Users, PyJWT)

```python
import jwt


def authorize(request) -> bool:
    try:
        jwt.decode(
            request.cookies.get("access_token", ""), SECRET, algorithms=["HS256"]
        )
    except jwt.InvalidTokenError:
        return False

    return True
```

### An auth proxy

Behind oauth2-proxy, Authelia or Cloudflare Access, the proxy logs the visitor in and passes who they are in a header. Keep the dashboard on `127.0.0.1`, so the proxy is the only way in:

```python
def authorize(request) -> bool:
    return request.headers.get("X-Forwarded-User") is not None
```

### HTTP Basic

Without an application to log in to, like a bot or a worker, the browser's own prompt does the job:

```python
import base64
import hmac

EXPECTED = "Basic " + base64.b64encode(b"admin:" + PASSWORD.encode()).decode()


def authorize(request) -> bool:
    return hmac.compare_digest(request.headers.get("Authorization", ""), EXPECTED)
```

Basic auth sends the password with every request. Outside a private network, serve the dashboard over HTTPS through a reverse proxy.
