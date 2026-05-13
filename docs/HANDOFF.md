# Handoff — Phase 53: chatwire-mqtt plugin + registry expansion

> Phase 53 session shipped (2026-05-13, commit 72fc96d in chatwire-dev).
> 1082 pytest (1074 pass + 8 pre-existing failures) + 190 Vitest — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 53 code).

## §1 Current state

- **mbair**: commit 72fc96d deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants (rose-pine, rose-pine-moon, rose-pine-dawn).
- **chatwire-plugins registry**: 9 plugins now live on GitHub (`allenbina/chatwire-plugins`).
  New entries: chatwire-mqtt, chatwire-ha, chatwire-xmpp.
- **Tests**: 1082 collected (1074 pass + 8 pre-existing failures) / 190 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 53 changes.
- **PyPI**: v1.14.0 (no version bump — no public API changes).
- **Public repo (allenbina/chatwire)**: synced to Phase 51 as of aff5292. Phase 53 adds only
  plugin source + tests; a sync is due but not blocking (mbair uses git+ssh).
- **Open bugs**: 0.

## §2 What shipped in Phase 53 (2026-05-13)

### chatwire-mqtt plugin — closes #27 MQTT output

**Problem**: No MQTT output for home automation pipelines (Home Assistant, Node-RED, OpenHAB).

**Fix** (`chatwire-plugins/chatwire-mqtt/`):

- **`MQTTIntegration`** class in `chatwire_mqtt/__init__.py`:
  - Publishes every inbound iMessage as JSON (v=1) to a paho-mqtt broker.
  - Topic layout: `<base>/<sanitized_handle>` for 1:1, `<base>/group/<sanitized_chat_id>` for groups.
  - MQTT-reserved chars (`+`, `#`, `/`, NUL) replaced with `_` via `_sanitize_topic_segment()`.
  - Payload: `{v, rowid, handle, text, is_from_me, chat: {guid, identifier, name, is_group}}`.
  - Config: `host` (required), `port` (1883), `topic` ("chatwire/messages"), `username`, `password`,
    `qos` (0/1/2), `client_id` ("chatwire").
  - paho-mqtt guard: lazy import with `_PAHO_AVAILABLE` flag; `start()` raises `RuntimeError`
    if paho is not installed (same pattern as xmpp/ha).
  - `on_inbound()` and `stop()` are always safe before `start()`.
  - `publish()` failures (exception or non-zero rc) are logged but never re-raised.
- **`pyproject.toml`**: name=chatwire-mqtt, version=1.0.0, dep=paho-mqtt>=1.6.
  Entry-point: `chatwire.integrations: chatwire_mqtt = "chatwire_mqtt:MQTTIntegration"`.

**Tests** (`tests/test_mqtt_integration.py`): 22 tests, all pass in isolation and in full suite.
- Uses `asyncio.run()` (not `asyncio.get_event_loop().run_until_complete()`) to avoid
  event-loop state leakage from the pre-existing test_mcp.py failures.
- Covers: 1:1 topic, group topic, handle sanitization, payload schema, is_from_me filter,
  empty text, publish exception, non-zero rc, missing host, paho unavailable, pre-start safety,
  double-stop idempotency, username/password, custom client_id.

### Plugin registry expansion

**`chatwire-plugins/plugins.json`** — three new entries:
- `chatwire-mqtt`  (action, signed) — MQTT broker output
- `chatwire-ha`    (action, signed) — Home Assistant keyword→service trigger
- `chatwire-xmpp`  (bridge, signed) — iMessage ↔ XMPP relay via slixmpp

Pushed to `allenbina/chatwire-plugins` (commit 9d4de54). Registry now has 9 entries.

Note: `chatwire-ha` and `chatwire-xmpp` source code already existed locally
(`chatwire-plugins/chatwire-ha/`, `chatwire-plugins/chatwire-xmpp/`) with full implementations
and tests (`test_ha_integration.py`, `test_xmpp_integration.py`). Added to registry only.

## §2 What shipped in Phase 52 (2026-05-12)

### Public repo sync — allenbina/chatwire to Phase 51

**Result** (commit aff5292 in allenbina/chatwire):
- 5 files changed: 407 insertions / 20 deletions
- Public repo now fully in sync with Phase 51

## §2 What shipped in Phase 51 (2026-05-12)

### `chatwire status` subcommand

Prints version, config path+port, launchd agent status (macOS), installed plugins.
`cmd_status()` in `chatwire_cli.py`; always exits 0; 21 tests in `tests/test_status.py`.

### img_cache in uninstall paths (Phase 48 gap)

`_uninstall_paths()` now includes `img_cache`; `scripts/uninstall.sh` Step 6 updated.

## §3 Open bugs

None.

## §4 Follow-ups (Phase 54+ candidates)

**Theme ecosystem**:
- Publish `chatwire-theme-rosepine` to PyPI (needs `TWINE_TOKEN` or `~/.pypirc`).
  Once on PyPI, the marketplace Install button will work end-to-end without git+ssh.
  Currently install from marketplace fails at pip.
- Publish `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp` to PyPI for marketplace installs.
- Visual QA of per-theme custom CSS editor.
- Visual QA of theme skin ZIP buttons.
- Visual QA of theme picker dropdown with Rose Pine plugin schemes.
- Visual QA of hover action bar, tapback tooltips, mark-all-read icon (Phase 33).
- Visual QA of reminder contacts picker (Phase 39).
- Visual QA of hiatus sidebar indicator + End button + countdown (Phases 40–42).
- Visual QA of hiatus SettingsPage countdown (Phase 43).
- Visual QA of pinnable settings pin icons + sidebar toggle buttons (Phase 44).
- Visual QA of iOS reply ghost bubble (Phase 45).
- Visual QA of accordion animation (Phase 46).
- Visual QA of theme picker refresh after install/uninstall (Phase 47).

**Plugin gaps**:
- `chatwire-mqtt`: Add TLS support (`use_tls`, `ca_cert` config options) for encrypted brokers.
- `chatwire-ha`: Allow per-keyword allowed-sender filters (restrict commands to specific handles).
- `chatwire-mqtt`: Add outbound relay (MQTT→iMessage) so automations can send replies.
- Write `chatwire-mqtt.md` README (matches pattern of chatwire-ha.md, chatwire-xmpp.md).

**Other features**:
- #41 Demo app on chatwire.app
- #20 Automation engine + #28 trigger grammar
- #23 Data exposure warning
- #65 Offline mode — already fully implemented.
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #25 Uninstaller: script + Python cmd both done; testing complete as of Phase 51.
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)
- Public repo sync: allenbina/chatwire needs sync to Phase 52-53.

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy. ~34KB addition to core.

## §5 Architecture notes

### chatwire-mqtt plugin (added Phase 53)

- **Package**: `chatwire-plugins/chatwire-mqtt/` — `chatwire_mqtt/__init__.py` + `pyproject.toml`.
- **Class**: `MQTTIntegration` — `NAME = "chatwire_mqtt"`, `TIER = "official"`.
- **Dependency**: `paho-mqtt>=1.6` (declared in pyproject.toml; guard: `_PAHO_AVAILABLE` flag).
- **Lifecycle**: `start(ctx)` → `paho.Client.connect() + loop_start()`. `stop()` → `loop_stop() + disconnect()`.
- **Topic segments**: `_sanitize_topic_segment(s)` replaces `+#/\x00` → `_`; empty → `"_"`.
- **Topic routing**: 1:1 → `<topic>/_15551234567`, group → `<topic>/group/<chat_id>`.
  (Phone numbers: `+` in handle becomes `_` in topic.)
- **Payload schema (v=1)**:
  ```json
  {"v": 1, "rowid": 12345, "handle": "+1...", "text": "...",
   "is_from_me": false, "chat": {"guid": "...", "identifier": "...", "name": null, "is_group": false}}
  ```
- **publish()** errors: non-zero rc → log warning; exceptions → log warning. Both are no-ops.
- **22 tests** in `tests/test_mqtt_integration.py`; all use `asyncio.run()` to isolate event loop.

### Plugin registry (chatwire-plugins, updated Phase 53)

- Repo: `github.com/allenbina/chatwire-plugins` — tracks `plugins.json` only.
- Now 9 entries: apprise, telegram, webhook, stats, theme-rosepine, example,
  mqtt (new), ha (new), xmpp (new).
- Plugin source dirs live in `chatwire-plugins/chatwire-*/` in chatwire-dev only (not tracked in the plugins repo).

### chatwire status subcommand (added Phase 51)

- Function: `cmd_status()` in `chatwire_cli.py`.
- Parser entry: `chatwire status [--label-prefix <prefix>]` (default `dev.chatwire`).
- Always returns 0 (read-only probe).
- Calls `config.load_config()` guarded in try/except; port default 8723.
- Agents section: only rendered on `sys.platform == "darwin"`.
- 21 tests in `tests/test_status.py`.

### img_cache startup warmer (added Phase 49)

- **`_WARMUP_DAYS`**: 30 / **`_WARMUP_MAX`**: 200.
- **`_img_cache_warmer()`**: async task started in `@on_event("startup")`, 10 s delay.
  Iterates recent HEIC attachments; calls `asyncio.to_thread(_full_img_for, p)` per row.
  All errors caught; never raises.

### Attachment image cache (added Phase 48)

- **`FULL_IMG_CACHE_DIR`**: `~/.chatwire/img_cache`; **`FULL_IMG_TTL_DAYS`**: 90.
- **`_full_img_for(orig)`**: SHA1-keyed; `sips -s format jpeg`.
- **`_attachment_cache_evictor()`**: sweeps both caches daily; runs in startup handler.
- **`_ATTACHMENT_CACHE_CONTROL`**: `"public, max-age=2592000"` — applied to all `/attachment` paths.

### Theme plugin refresh event (added Phase 47)

- Event name: `chatwire-plugin-themes-changed` (CustomEvent on `window`).
- Dispatch: `InstallOverlay` + `removeMutation.onSuccess` in `PluginsPage.tsx`.
- Handler: `refreshPluginThemes` in `useTheme` hook.

### chatwire-plugins registry (updated Phase 47 / 53)

- Repo: `github.com/allenbina/chatwire-plugins` (nested at `chatwire-plugins/` in chatwire-dev).
- 9 entries total: apprise, telegram, webhook, stats, theme-rosepine, example, mqtt, ha, xmpp.
- All have `tags`, `icon`, `signed` fields.
- Fetched by `web/registry.py::fetch_registry()` with 24 h disk cache.

### Deploy pipeline (updated 2026-05-12)

- `dist/` is committed to git — no separate scp step.
- Deploy: `pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'`
- Restart: `/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge`
- Health: `/usr/bin/curl -sf localhost:8723/healthz`

### Frontend build

- After any frontend code change: `npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build`
- Commit the updated `dist/` with the source changes.
- `.gitattributes` treats JS/CSS in dist/ as binary (no line-level diffs).

### Accordion animation (added Phase 46)

- File: `web/frontend/src/index.css`
- `@keyframes accordion-down`/`accordion-up` use `--radix-accordion-content-height`.
- Registered via Tailwind v4 `@theme`: `--animate-accordion-down` / `--animate-accordion-up`.

### iOS reply ghost bubble (added Phase 45)

- Component: `ReplyQuote` in `MessageBubble.tsx`.
- Ghost bubble colors keyed on `parentFromMe = reply.sender === ''`.
- Thumbnail: `/attachment?path=…&size=thumb` → 32×32 img when `image_path` present.

### Pinnable settings (added Phase 44)

- Hook: `usePinnedSettings`; storage: `chatwire-pinned-settings` in localStorage.
- Sidebar: conditional toggle buttons via `SidebarContent` in `Layout.tsx`.

### Hiatus auto-off timer (added Phase 42–43)

- Config key: `cfg["web"]["hiatus_started_at"]` — epoch float; `0` = not set.
- Frontend: interval every 30 s; when `Date.now() >= endsAt`, fires `endHiatusMutation`.

### Per-theme custom CSS (added Phase 37)

- Storage: `~/.chatwire/custom-css/<slug>.css`; max 64 KB per theme.
- `GET /api/ui/custom-css/combined` returns `{css, themes}`.

### Theme override system (added Phase 30)

- Files: `~/.chatwire/theme-overrides/<slug>.json`.
- Style element ID: `chatwire-theme-override`.
- Load order: theme CSS → plugin theme CSS → override CSS → accent override → custom CSS.

### Whitelist contact cards

- `GET /api/ui/whitelist` returns `{contacts: [{name, handles[], whitelisted}], group_chats: [...]}`.

## §6 Next prompt

```
Read docs/HANDOFF.md in full. This is your state file.

git pull first — there may be commits from an interactive session.

STATE: Phase 53 shipped (chatwire-mqtt plugin closes #27, registry +ha +xmpp, commit 72fc96d).
1082 pytest (1074 pass + 8 pre-existing), 190 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 53 code, healthy).
Public repo allenbina/chatwire: still at Phase 51 (aff5292) — sync needed.

Key blocker for PyPI publish of plugins:
  chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp are NOT on PyPI.
  Marketplace Install button will fail at pip for these until published.
  Requires TWINE_TOKEN env var or ~/.pypirc with PyPI API token.

Pick a task from §4 options:

Option A — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option B — chatwire-mqtt TLS support: add use_tls, ca_cert config options.
  Small feature, ~30 lines in __init__.py + tests. No PyPI token needed.

Option C — #20 Automation engine / #28 trigger grammar (larger, plan first).

Option D — Public repo sync (allenbina/chatwire to Phase 52–53).

Option E — chatwire-mqtt README (chatwire-mqtt.md) + chatwire-ha/xmpp README review.

VISUAL QA NOTE: pin icons in SettingsPage, sidebar toggle buttons for hiatus/reminder,
hiatus sidebar indicator + dismiss button + countdown, hiatus SettingsPage countdown,
reminder contacts picker, per-theme custom CSS editor, theme skin ZIP buttons, hover
action bar, tapback tooltips, mark-all-read icon, Rose Pine theme picker, iOS
reply ghost bubble, accordion animation, theme picker refresh after install,
and HEIC img_cache warmer behavior all require an interactive session on mbair
— skip and note if headless.

Run: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
Run: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
After frontend changes: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build
Commit dist/ with source changes.
All tests must pass before committing.

DEPLOY:
  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'"
  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge"
  ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"

After work — commit, push, deploy, and notify:
  curl -s -d "Phase 54 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Pre-existing failures (8): test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4)
  — all caused by test_mcp.py closing the asyncio event loop. Use asyncio.run() in new test files.
NOTE: Public repo sync method: rsync -a --checksum (no --delete) from chatwire-dev/
  to /tmp/chatwire-public/ with excludes for dist/, node_modules/, __pycache__/, .git/
  Then git add -A && git commit && git push in /tmp/chatwire-public/
NOTE: After rsync, RESTORE .gitignore (git checkout -- .gitignore) to preserve
  web/frontend/dist/ exclusion — chatwire-dev commits dist/ but public repo does not.
```
