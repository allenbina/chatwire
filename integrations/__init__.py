"""chatwire integrations package.

Each chat surface (Telegram, the web UI, webhook-out, future Slack/Matrix/etc)
lives in `integrations/<name>/` and exposes a class that satisfies
`integrations.base.Integration`.

The bridge core auto-discovers built-in integrations by walking this directory
at startup. Third-party pip-installable plugins register via the
`chatwire.integrations` entry-point group; see docs/OPEN_SOURCE_PLAN.md
Phase 4 for the contract.
"""
from integrations.base import (
    BridgeContext,
    InboundMessage,
    Integration,
    SendOutcome,
    SendTarget,
)

__all__ = [
    "BridgeContext",
    "InboundMessage",
    "Integration",
    "SendOutcome",
    "SendTarget",
]
