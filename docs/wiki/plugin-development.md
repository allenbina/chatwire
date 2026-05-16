# Plugin Development

chatwire plugins extend the bridge with new integrations. There are four tiers,
each with a different level of data access.

---

## Plugin tiers

| Tier | Data access | Use case |
|---|---|---|
| `ui` | None — CSS/JS only | Themes, custom UI widgets |
| `notify` | Sender name, group info, timestamp | Push notifications, LED alerts |
| `official` | Full message text + send capability | Chat relay, AI assistants |
| `core` | Full BridgeContext (internal only) | Built-in components (content filter, etc.) |

Third-party plugins start at `notify` and require maintainer review to advance
to `official`.

---

## Quick start

### 1. Install the SDK

```bash
pip install chatwire-sdk
# — or in-tree during development:
pip install -e packages/sdk/
```

### 2. Scaffold a plugin

```bash
chatwire-sdk scaffold my_plugin
cd my_plugin
```

This creates:

```
my_plugin/
├── my_plugin/__init__.py     # Integration class
├── pyproject.toml            # Entry point: chatwire.integrations
└── README.md
```

### 3. Implement hooks

```python
from chatwire_sdk import BaseIntegration, chatwire_plugin, SanitizedEvent

@chatwire_plugin
class MyPlugin(BaseIntegration):
    NAME = "my_plugin"
    TIER = "notify"
    DISPLAY_NAME = "My Plugin"
    DESCRIPTION = "Sends a push notification on new messages."
    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "webhook_url": {"type": "string", "title": "Webhook URL"},
        },
        "required": ["webhook_url"],
    }

    async def on_startup(self) -> None:
        self.log_info("plugin ready")

    async def on_notify(self, event: SanitizedEvent) -> None:
        if event.sender_display_name:
            self.log_info(f"new message from {event.sender_display_name}")
        # send push notification ...
```

### 4. Install into chatwire

```bash
# During development:
pipx inject chatwire -e /path/to/my_plugin

# From PyPI:
pipx inject chatwire my_plugin
```

### 5. Enable in the web UI

Open **Settings → Plugins**, find your plugin, and toggle it on.

---

## Settings schema

The `SETTINGS_SCHEMA` dict is a JSON Schema object. The web UI renders form
controls automatically:

```python
SETTINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "api_key": {
            "type": "string",
            "title": "API Key",
            "description": "From your dashboard at example.com",
        },
        "timeout_s": {
            "type": "number",
            "title": "Timeout (seconds)",
            "default": 10,
            "minimum": 1,
            "maximum": 60,
        },
        "mode": {
            "type": "string",
            "title": "Mode",
            "enum": ["fast", "reliable"],
            "default": "fast",
        },
    },
    "required": ["api_key"],
}
```

Read config values at runtime:

```python
async def on_startup(self) -> None:
    cfg = self._ctx.plugin_config     # freshly loaded from disk each call
    self.api_key = cfg.get("api_key", "")
```

---

## Structured logging

Use the context log methods instead of `print()` or `logging`:

```python
self.log_info("plugin started")
self.log_warn("rate limit approaching")
self.log_error(f"API call failed: {exc}")
```

Or equivalently via the context object:

```python
self._ctx.log_info("message")
```

### `LOGS_VISIBLE` — controlling log visibility

By default, log entries appear in the chatwire Log Viewer at `/logs`. Set
`LOGS_VISIBLE = False` to redirect logs to a private per-plugin file
(`~/.chatwire/plugins/<name>/plugin.log`) instead:

```python
class MyPlugin(BaseIntegration):
    NAME = "my_plugin"
    LOGS_VISIBLE = False    # keep diagnostic logs out of the shared viewer
```

You can still use Python's `logging` module for internal debug output — those
lines go to `~/Library/Logs/chatwire/stderr.log` regardless of `LOGS_VISIBLE`.

---

## Official-tier plugins (send capability)

`official` plugins receive `OfficialMessage` (sender name + text + attachment
bytes) and can send replies via `self._ctx.send_text()`. They require:

1. Review and code signing by the chatwire maintainer.
2. Published to PyPI under the `chatwire-` namespace.

The send API uses opaque conversation IDs — raw phone numbers and email
addresses are never exposed to the plugin:

```python
from chatwire_sdk import BaseIntegration, OfficialMessage  # type: ignore

class MyOfficialPlugin(BaseIntegration):
    NAME = "my_official"
    TIER = "official"

    async def on_official_message(self, msg: OfficialMessage) -> None:
        if "hello" in msg.text.lower():
            await self._ctx.send_text(msg.conversation_id, "Hello back!")
```

---

## Entry point

Register your integration class in `pyproject.toml`:

```toml
[project.entry-points."chatwire.integrations"]
my_plugin = "my_plugin:MyPlugin"
```

chatwire discovers all `chatwire.integrations` entry points at startup and
verifies their signatures before loading.

---

## Publishing

1. Bump the version in `pyproject.toml`
2. `python -m build && twine upload dist/*`
3. Users install with: `pipx inject chatwire my_plugin`
4. The chatwire maintainer must sign the distribution for it to load in
   production (`official` tier requires this; `notify` and `ui` do not).
