import asyncio
import errno
import logging
import os
import threading
from collections.abc import Callable
from contextlib import suppress

from aiohttp import web

AppFactory = Callable[[], web.Application]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1212

STARTUP_TIMEOUT = 10.0
SHUTDOWN_TIMEOUT = 5.0
CLEANUP_TIMEOUT = 2.0
ELECTION_RETRY_INTERVAL = 2.0

logger = logging.getLogger("dachshund")


class Runtime:
    """The dashboard server, running inside the host process.

    The runtime owns a background thread with its own asyncio event loop. It
    never touches the host's loop (if it even has one), so it behaves the same
    whether the host is a blocking WSGI application or an asyncio bot.

    It serves whatever application the factory builds, and calls the factory
    again on every start so a stopped runtime can be started back up.

    Under a multi-worker server, several `Runtime`s share one host:port.
    Only one can bind it, so a taken port doesn't fail `start()`, it stands
    by and keeps retrying in the background, that's how a dead winner gets
    replaced without a restart. See `is_serving`.
    """

    def __init__(
        self,
        create_app: AppFactory,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.create_app = create_app
        self.host = host
        self.requested_port = port

        self._port: int | None = None
        self._pid: int | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    @property
    def port(self) -> int:
        """The port the dashboard is bound to."""
        if self._port is None:
            if self.is_running:
                raise RuntimeError(
                    "This worker hasn't won the port-bind election yet, "
                    "another worker is currently serving the dashboard."
                )
            raise RuntimeError("The runtime is not running.")
        return self._port

    @property
    def url(self) -> str:
        """The address the dashboard is reachable at."""
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        """Whether the runtime thread is alive."""
        if self._pid is not None and self._pid != os.getpid():
            return False
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_serving(self) -> bool:
        """Whether this worker currently holds the dashboard port."""
        return self.is_running and self._port is not None

    def start(self) -> None:
        """Start the runtime and wait for it to accept connections."""
        if self.is_running:
            return

        self._forget()
        self._ready.clear()
        self._error = None
        self._pid = os.getpid()

        self._thread = threading.Thread(
            target=self._run,
            name="dachshund-runtime",
            daemon=True,
        )
        self._thread.start()

        if not self._ready.wait(STARTUP_TIMEOUT):
            self.stop()
            raise RuntimeError(
                f"The runtime did not start within {STARTUP_TIMEOUT} seconds."
            )

        if self._error is not None:
            self.stop()
            raise self._error

    def stop(self) -> None:
        """Stop the runtime and wait for its thread to exit."""
        if self._pid is not None and self._pid != os.getpid():
            self._forget()
            return

        loop, shutdown, thread = self._loop, self._shutdown, self._thread

        if loop is not None and shutdown is not None:
            try:
                loop.call_soon_threadsafe(shutdown.set)
            except RuntimeError:
                pass

        if thread is not None:
            thread.join(SHUTDOWN_TIMEOUT)

            if thread.is_alive():
                logger.warning(
                    "The runtime thread is still running %s seconds after being "
                    "asked to stop.",
                    SHUTDOWN_TIMEOUT,
                )
                return

        self._forget()

    def _forget(self) -> None:
        self._thread = None
        self._loop = None
        self._shutdown = None
        self._port = None
        self._pid = None

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            loop.run_until_complete(self._serve())
        except BaseException as error:
            if self._error is None:
                self._error = error
            logger.exception("The dashboard runtime stopped unexpectedly.")
        finally:
            asyncio.set_event_loop(None)
            loop.close()
            self._loop = None
            self._ready.set()

    async def _serve(self) -> None:
        self._shutdown = asyncio.Event()
        runner = web.AppRunner(
            self.create_app(),
            shutdown_timeout=CLEANUP_TIMEOUT,
        )

        try:
            await runner.setup()
        except BaseException as error:
            self._error = error
            self._ready.set()
            await runner.cleanup()
            return

        # `runner.setup()` already started the event pump, so this worker
        # keeps persisting events below whether or not it wins the port.
        standing_by = False

        try:
            await self._try_bind(runner)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                self._error = error
                self._ready.set()
                await runner.cleanup()
                return

            standing_by = True
            logger.info(
                "%s:%s is already taken, standing by and retrying in the "
                "background in case the current owner goes away.",
                self.host,
                self.requested_port,
            )

        self._ready.set()

        try:
            while standing_by and not self._shutdown.is_set():
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._shutdown.wait(), ELECTION_RETRY_INTERVAL
                    )

                if self._shutdown.is_set():
                    break

                with suppress(OSError):
                    await self._try_bind(runner)
                    logger.info(
                        "Won the port-bind election, now serving on %s.", self.url
                    )
                    break

            await self._shutdown.wait()
        finally:
            await runner.cleanup()

    async def _try_bind(self, runner: web.AppRunner) -> None:
        site = web.TCPSite(runner, self.host, self.requested_port)

        try:
            await site.start()
        except OSError:
            # `site.start()` registers with the runner before it binds, so
            # a failed attempt has to be stopped explicitly, or it's a
            # dead entry the runner keeps around forever.
            await site.stop()
            raise

        self._port = _resolve_port(runner, self.requested_port)


def _resolve_port(runner: web.AppRunner, fallback: int) -> int:
    for address in runner.addresses:
        if isinstance(address, tuple) and len(address) >= 2:
            return int(address[1])
    return fallback
