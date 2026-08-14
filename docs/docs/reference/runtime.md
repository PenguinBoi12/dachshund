# Runtime

`Runtime` is the dashboard server itself: a background thread with its own asyncio event loop, serving whatever aiohttp application its factory builds. It never touches the host process's own event loop, so it behaves the same whether the host is a blocking WSGI application or an asyncio bot.

Most applications never touch `Runtime` directly; `Dashboard` owns one, and `dachshund.init()`/`dachshund.shutdown()` start and stop it.

::: dachshund.runtime.boot.Runtime
