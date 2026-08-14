from aiohttp import web
from jinja2 import Environment

from dachshund.registry import Dashboard

CLIENTS: web.AppKey[set[web.WebSocketResponse]] = web.AppKey("clients")
DASHBOARD = web.AppKey("dashboard", Dashboard)
TEMPLATES = web.AppKey("templates", Environment)
