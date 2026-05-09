"""Pure helpers for launchd service status and control.

Extracted from web.main so they can be unit-tested without importing the
full FastAPI application (which has side-effectful module-level code).
"""
from __future__ import annotations

LAUNCHD_SERVICES: dict[str, str] = {
    "bridge": "dev.chatwire.bridge",
    "web": "dev.chatwire.web",
    "keepawake": "dev.chatwire.keepawake",
}


def parse_service_status(launchctl_output: str) -> dict:
    """Parse `launchctl list` output into a status dict.

    Returns ``{bridge: bool, web: bool, keepawake: bool}`` where ``True``
    means the service label appears in the launchctl output (i.e. it is
    registered / running).  Works on partial output such as the result of
    piping through grep.
    """
    result: dict = {k: False for k in LAUNCHD_SERVICES}
    for line in launchctl_output.splitlines():
        for key, label in LAUNCHD_SERVICES.items():
            if label in line:
                result[key] = True
    return result
