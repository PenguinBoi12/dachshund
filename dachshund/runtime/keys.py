from aiohttp import web
from jinja2 import Environment

from dachshund.registry import Dashboard

# Each open page, mapped to the dashboard page it shows, None to be sent everything.
CLIENTS: web.AppKey[dict[web.WebSocketResponse, str | None]] = web.AppKey("clients")
DASHBOARD = web.AppKey("dashboard", Dashboard)
TEMPLATES = web.AppKey("templates", Environment)
