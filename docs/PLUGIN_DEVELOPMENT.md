# Plugin Development Guide

chatwire supports two complementary plugin surfaces:

1. **Python backend plugins** — integrate with the iMessage bridge via
   `chatwire-sdk` (`BaseIntegration`).
2. **React frontend plugins** — inject UI components into named _slots_ in
   the web app.

The Stats integration (`integrations/stats/`) demonstrates both surfaces
end-to-end and is the canonical reference implementation.

---

## Table of contents

1. [Scaffold a backend plugin](#1-scaffold-a-backend-plugin)
2. [BaseIntegration lifecycle hooks](#2-baseintegration-lifecycle-hooks)
3. [Register a frontend slot component](#3-register-a-frontend-slot-component)
4. [Available slots](#4-available-slots)
5. [End-to-end example: Stats plugin](#5-end-to-end-example-stats-plugin)
6. [Publishing your plugin](#6-publishing-your-plugin)

---

## 1. Scaffold a backend plugin

Install the SDK (in-tree during development):

```bash
pip install -e packages/sdk
# or, once published:
pip install chatwire-sdk
```

Use the CLI to generate a fully wired plugin directory:

```bash
chatwire-plugin init my_greeter
```

This creates:

```
my_greeter/
  pyproject.toml          ← package metadata + chatwire.plugins entry point
  my_greeter/
    __init__.py
    plugin.py             ← BaseIntegration subclass decorated with @chatwire_plugin
  tests/
    __init__.py
    test_plugin.py        ← pytest smoke tests
  README.md
```

Run the generated tests to confirm everything wires up:

```bash
cd my_greeter
pip install -e ".[dev]"
pytest
```

---

## 2. BaseIntegration lifecycle hooks

Every backend plugin subclasses `BaseIntegration` and overrides the hooks
it needs. All hooks have no-op defaults, so you only implement what matters.

```python
from chatwire_sdk import BaseIntegration, chatwire_plugin

@chatwire_plugin
class GreeterIntegration(BaseIntegration):
    NAME = "greeter"                       # stable snake_case identifier
    DISPLAY_NAME = "Greeter"               # shown in the settings UI
    DESCRIPTION = "Sends a welcome message on startup."
    VERSION = "1.0.0"
    AUTHOR = "Your Name"

    SETTINGS_SCHEMA = {                    # JSON Schema → settings form
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable Greeter",
            },
            "message": {
                "type": "string",
                "default": "Hello!",
                "title": "Greeting text",
            },
        },
    }

    async def on_startup(self) -> None:
        """Called once when the chatwire bridge starts."""
        print(f"Greeter says: {self.config.get('message', 'Hello!')}")

    async def on_shutdown(self) -> None:
        """Called once when the bridge shuts down."""

    async def on_message_received(self, msg) -> None:
        """Called for every inbound iMessage.

        msg.text        — message body (str)
        msg.handle      — sender handle, e.g. "+15551234567"
        msg.is_from_me  — bool
        msg.chat_guid   — group chat GUID or None for 1:1
        """

    async def on_message_sent(self, msg) -> None:
        """Called after every outbound message is accepted.

        Same fields as on_message_received, plus msg.outcome.status.
        """
```

### Hook reference

| Hook | When called | Typical use |
|------|-------------|-------------|
| `on_startup()` | Bridge start | Open connections, start tasks |
| `on_shutdown()` | Bridge stop | Cancel tasks, flush state |
| `on_message_received(msg)` | Every inbound iMessage | Forward to Telegram, log to DB |
| `on_message_sent(msg)` | After every outbound send | Analytics, confirmations |

### Reading config

```python
# config dict is passed at instantiation from config.json
# Access it via self.config:
api_key = self.config.get("api_key", "")
enabled = self.config.get("enabled", False)
```

### Accessing the bridge

The bridge context is available as `self._ctx` after `on_startup()` runs:

```python
async def on_startup(self) -> None:
    # self._ctx is a BridgeContext — see integrations/base.py
    name = self._ctx.name_for("+15551234567")
```

---

## 3. Register a frontend slot component

Frontend plugins are React components registered in named slots using
`window.chatwire.registerSlot()` (or the direct import from `registry.ts`).

### Option A — Direct import (in-tree / bundled)

```typescript
// src/main.tsx (or any module loaded before the first render)
import { registerSlot } from './plugins/registry'
import { MyWidget } from './plugins/MyWidget'

registerSlot('sidebar.panel', MyWidget, { key: 'my-widget' })
```

### Option B — External script (packaged plugin)

Plugin bundles served by your integration's FastAPI route can call the global
API after the chatwire app boots:

```html
<!-- Injected by your plugin's FastAPI route -->
<script src="/plugins/my_plugin/bundle.js" defer></script>
```

```javascript
// my_plugin/bundle.js
window.chatwire?.registerSlot('sidebar.panel', function MyWidget(props) {
  // Minimal vanilla React (window.React must be available)
  return window.React.createElement('div', null, 'Hello from my plugin!')
}, { key: 'my-plugin' })
```

### Slot component contract

Every slot component receives `SlotProps`:

```typescript
interface SlotProps {
  slot: SlotName          // which slot this render is for
  [key: string]: unknown  // extra props forwarded from <SlotRenderer>
}
```

Slots are rendered inside `<PluginErrorBoundary>` — a crash in your component
shows an inline error chip instead of taking down the whole UI.

---

## 4. Available slots

| Slot name | Host component | Extra props forwarded |
|-----------|---------------|----------------------|
| `message.toolbar` | `MessageBubble` | `msgRowid: number`, `fromMe: boolean` |
| `sidebar.panel` | `Layout` (sidebar) | — |
| `settings.page` | `SettingsPage` | — |
| `compose.extension` | `ComposeBox` | `handle: string` |

### `message.toolbar`

Rendered after the timestamp in each message bubble. Receives the message's
`rowid` and a `fromMe` flag so you can show per-message actions.

```tsx
function ReactionButton({ msgRowid, fromMe }: SlotProps) {
  if (fromMe) return null
  return <button onClick={() => react(msgRowid)}>👍</button>
}
registerSlot('message.toolbar', ReactionButton)
```

### `sidebar.panel`

Rendered inside the conversation list scroll area, below all conversations.
Ideal for compact summary widgets (stats, pending tasks, announcements).

```tsx
function MyPanel(_props: SlotProps) {
  return <div className="px-3 py-2 text-xs">Hello sidebar!</div>
}
registerSlot('sidebar.panel', MyPanel)
```

### `settings.page`

Rendered after the "About" accordion section. Use this to expose your
plugin's own settings inside the existing settings UI.

```tsx
function MySettings(_props: SlotProps) {
  return (
    <div className="border-b border-[--color-border] px-5 py-4 text-sm">
      <h3 className="font-medium mb-2">My Plugin Settings</h3>
      {/* your settings form */}
    </div>
  )
}
registerSlot('settings.page', MySettings)
```

### `compose.extension`

Rendered above the message input row in `ComposeBox`. Receives the active
`handle` so you can show contact-specific suggestions or quick-replies.

```tsx
function QuickReplies({ handle }: SlotProps) {
  return (
    <div className="flex gap-1 mb-1">
      <button onClick={() => send(handle, 'On my way!')}>On my way!</button>
    </div>
  )
}
registerSlot('compose.extension', QuickReplies)
```

---

## 5. End-to-end example: Stats plugin

The built-in Stats integration demonstrates the full plugin lifecycle.

### Backend (`integrations/stats/__init__.py`)

```python
from chatwire_sdk import BaseIntegration, chatwire_plugin

@chatwire_plugin
class StatsIntegration(BaseIntegration):
    NAME = "stats"
    DISPLAY_NAME = "Message statistics"
    DESCRIPTION = "Messaging analytics computed locally from your chat.db."

    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": False},
            "date_range": {
                "type": "string",
                "enum": ["30d", "90d", "365d", "all"],
                "default": "30d",
            },
        },
    }
```

### API endpoint (`web/api_ui.py`)

`GET /api/ui/stats` — returns JSON: sent/received totals, top contacts,
hour-of-day distribution, day-of-week distribution, top groups.
Returns `{"enabled": false}` when the integration is disabled.

### Frontend (`web/frontend/src/plugins/StatsWidget.tsx`)

```tsx
import { useQuery } from '@tanstack/react-query'

export function StatsWidget() {
  const { data } = useQuery({
    queryKey: ['stats-widget'],
    queryFn: () => fetch('/api/ui/stats').then(r => r.json()),
    staleTime: 5 * 60_000,
  })

  if (!data?.enabled) return null
  return (
    <div className="px-3 py-3 text-xs text-[--color-text-muted]">
      ↑ {data.sent_total} sent · ↓ {data.received_total} received
    </div>
  )
}
```

### Registration (`web/frontend/src/main.tsx`)

```typescript
import { registerSlot } from './plugins/registry'
import { StatsWidget } from './plugins/StatsWidget'

registerSlot('sidebar.panel', StatsWidget, { key: 'stats-widget' })
```

The widget self-hides when the integration is disabled — no configuration
of the slot registration is needed.

---

## 6. Publishing your plugin

> Publishing support is planned for Phase 7 (CI/CD). These are the intended
> steps once the infrastructure is in place.

1. **Backend**: Publish `chatwire-<name>` to PyPI with a `chatwire.plugins`
   entry point pointing at your `BaseIntegration` subclass. Users install
   with `pip install chatwire-<name>`.

2. **Frontend**: Bundle your slot components with Vite/esbuild into a single
   JS file. Serve it from a FastAPI route in your integration and inject the
   `<script>` tag via a Jinja2 template hook or the React slot system.

3. **Discovery**: The chatwire bridge auto-discovers plugins via the
   `chatwire.plugins` entry point group using `importlib.metadata`.

Until Phase 7 ships, install plugins in developer mode:

```bash
pip install -e /path/to/my_plugin
```
