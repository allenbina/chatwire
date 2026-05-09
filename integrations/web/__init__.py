"""Web UI integration.

Runs the existing FastAPI app from `web/main.py` in-process under a
programmatically-driven `uvicorn.Server`, so the web UI fits the same
Integration shape as Telegram and webhook. Two operating modes coexist:

  - **In-process** (this module): the bridge core spawns uvicorn as a task
    inside `bridge.py`'s event loop. The `BridgeContext` is stashed on
    `app.state.ctx`; future work will redirect `/send` through
    `ctx.send_text` / `ctx.send_file` for centralized echo dedup.
  - **Standalone** (`web/main.py:main()`): the original launchd-driven
    uvicorn process. Live installs (the author's Mac) keep using this until
    a coordinated cutover; the in-process path is opt-in via
    `integrations.web.enabled = true` in config.json.

Both modes serve the same FastAPI app object, so feature parity is free —
only the lifecycle and the chat-send routing differ.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from integrations.base import BridgeContext, InboundMessage

log = logging.getLogger("chatwire.web")


class WebIntegration:
    NAME = "web"
    DISPLAY_NAME = "Web UI"
    DESCRIPTION = "Run the web interface in-process"
    ICON = "🌐"

    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Run the web UI in-process",
                "description": (
                    "When true, `chatwire` hosts the web UI itself "
                    "instead of relying on a separate launchd `web` agent. "
                    "Mutually exclusive with the standalone web service — "
                    "stop one before enabling the other."
                ),
            },
            "bind": {
                "type": "string",
                "default": "127.0.0.1",
                "title": "Bind address",
                "description": (
                    "Network interface to listen on. Stay on 127.0.0.1 "
                    "unless you have an auth layer in front (Tailscale, "
                    "Cloudflare Access, reverse proxy with magic-link, "
                    "etc.)."
                ),
            },
            "port": {
                "type": "integer",
                "default": 8723,
                "minimum": 1,
                "maximum": 65535,
                "title": "Port",
            },
        },
    }

    def __init__(self, config: dict[str, Any]):
        self._bind: str = config.get("bind", "127.0.0.1")
        self._port: int = int(config.get("port", 8723))
        self._ctx: BridgeContext | None = None
        self._server = None  # type: ignore[assignment]
        self._task: asyncio.Task | None = None

    async def start(self, ctx: BridgeContext) -> None:
        # Add the repo root to sys.path so `from web import main` works
        # whether we're running from a source checkout or a wheel install.
        repo_root = Path(__file__).resolve().parent.parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from web import main as web_main  # noqa: E402 — lazy import keeps fastapi out of bridge core
        import uvicorn

        web_main.app.state.ctx = ctx
        self._ctx = ctx

        config = uvicorn.Config(
            app=web_main.app,
            host=self._bind,
            port=self._port,
            log_level="info",
            lifespan="on",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        # uvicorn's default signal-handler install grabs SIGINT/SIGTERM and
        # treats them as "exit cleanly". bridge.py owns those signals; if
        # uvicorn intercepts them the bridge core never sees the shutdown.
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

        self._task = asyncio.create_task(self._server.serve(), name="web-uvicorn")
        # Yield once so uvicorn's startup hooks (push tailer, thumb evictor)
        # have a chance to run before start() returns. Not strictly required —
        # the integration is "ready" the moment the task is scheduled — but
        # makes the `INFO web integration started` log line strictly after
        # uvicorn's `Application startup complete`.
        await asyncio.sleep(0)
        log.info("web integration started on http://%s:%d", self._bind, self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await self._task
            except Exception:
                log.exception("web integration shutdown raised; continuing")
            self._task = None
        self._server = None
        log.info("web integration stopped")

    async def on_inbound(self, msg: InboundMessage) -> None:
        # The web UI reads chat.db directly and tails mirror.jsonl for live
        # updates over SSE — it doesn't consume the inbound fan-out.
        # Implementing this method is required by the Integration Protocol;
        # leaving it as a no-op is the right shape.
        return
