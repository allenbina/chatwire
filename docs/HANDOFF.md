# Handoff — Phase 55: chatwire-ha allowed_senders + ha.md README

> Phase 55 session shipped (2026-05-13, commits a621b5b, 0a388c9 in chatwire-dev).
> 1090 pytest (1082 pass + 8 pre-existing failures) + 190 Vitest — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 55 code).

## §1 Current state

- **mbair**: commit 0a388c9 deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants (rose-pine, rose-pine-moon, rose-pine-dawn).
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1090 collected (1082 pass + 8 pre-existing failures) / 190 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 55 changes.
- **PyPI**: v1.14.0 (no version bump — no public API changes; plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: NOT yet synced to Phase 55 (last sync: Phase 54 / 6879d85).
- **Open bugs**: 0.

## §2 What shipped in Phase 55 (2026-05-13)

### chatwire-ha: per-command allowed_senders filter

**Problem**: Any iMessage sender could trigger HA commands, even unknown numbers.

**Fix** (`chatwire-plugins/chatwire-ha/chatwire_ha/__init__.py`):

- **New per-command field**: `allowed_senders` — optional list of handles (phone numbers or
  email addresses). When non-empty, only senders in the list trigger the command.
  Empty or absent = any sender (backward compatible).
- **`__init__`**: stores `allowed_senders` as a `frozenset` of lowercased handles for O(1) lookup.
- **`on_inbound`**: after keyword match, checks `msg.handle.lower()` against the frozenset.
  If not in set, logs at DEBUG and silently returns — no reply, no HA call.
- **Matching**: case-insensitive (lowercased both sides); exact on phone numbers.
- **`SETTINGS_SCHEMA`**: new `allowed_senders` array field per command item.
- **Docstring**: updated with per-sender filter example and explanation.
- **7 new tests** in `TestAllowedSenders` class (`tests/test_ha_integration.py`).
  Total HA tests: 22.

### docs/plugins/ha.md

**New file**: `docs/plugins/ha.md`

Covers: what it does, install command, configuration walkthrough, settings reference
table (all fields including `allowed_senders`), minimal config, full config with
`allowed_senders`, how the per-sender filter works, keyword matching rules, HA automation
+ scene config examples, troubleshooting FAQ.

## §2 What shipped in Phase 54 (2026-05-13)

### chatwire-mqtt: TLS support

**Problem**: No encrypted broker support — cleartext only.

**Fix** (`chatwire-plugins/chatwire-mqtt/chatwire_mqtt/__init__.py`):

- **Two new config keys**:
  - `use_tls` (bool, default `false`) — enable TLS/SSL.
  - `ca_cert` (str, default `""`) — path to PEM CA cert; blank = system CA bundle.
- **`start()` change**: when `use_tls=true`, calls `client.tls_set(ca_certs=<path or None>)`
  before `connect()`. If `tls_set()` raises, wraps as `RuntimeError("TLS setup failed: ...")`.
- **`SETTINGS_SCHEMA`**: two new entries (`use_tls` at `x-ui-order: 8`, `ca_cert` at `9`).
- **Docstring**: updated with TLS configuration example.
- **9 new tests** in `TestTLS` class (`tests/test_mqtt_integration.py`).
  Total MQTT tests: 31.

### chatwire-mqtt: plugin README

**New file**: `docs/plugins/mqtt.md`

Covers: what it does, install command, configuration walkthrough, topic layout with
examples, full JSON payload schema (v=1), settings reference table (all 10 config keys),
minimal config, full TLS config, Home Assistant automation YAML example, troubleshooting FAQ.

### Public repo sync (allenbina/chatwire) — Phases 52–54

Synced `allenbina/chatwire` public repo from Phase 51 → Phase 54 (commit 6879d85).
**Not yet synced to Phase 55** — do this in the next session or a dedicated sync pass.

## §3 Open bugs

None.

## §4 Follow-ups (Phase 56+ candidates)

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine` to PyPI — marketplace Install button currently fails at pip.
- Publish `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp` to PyPI.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Public repo sync**:
- Sync `allenbina/chatwire` to Phase 55 (commits a621b5b, 0a388c9).
  Use rsync method from §6 notes. Remember to restore .gitignore after rsync.

**Plugin gaps**:
- `chatwire-mqtt`: Add outbound relay (MQTT→iMessage) so automations can send replies.
- Write `docs/plugins/xmpp.md` README (matches pattern of mqtt.md / ha.md).

**Other features**:
- #41 Demo app on chatwire.app
- #20 Automation engine + #28 trigger grammar
- #23 Data exposure warning
- #65 Offline mode — already fully implemented.
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Visual QA** (requires interactive mbair session):
- Per-theme custom CSS editor, theme skin ZIP buttons, theme picker with Rose Pine schemes
- Hover action bar, tapback tooltips, mark-all-read icon (Phase 33)
- Reminder contacts picker (Phase 39)
- Hiatus sidebar indicator + End button + countdown (Phases 40–42), SettingsPage countdown (Phase 43)
- Pinnable settings pin icons + sidebar toggle buttons (Phase 44)
- iOS reply ghost bubble (Phase 45)
- Accordion animation (Phase 46)
- Theme picker refresh after install/uninstall (Phase 47)
- HEIC img_cache warmer behavior (Phase 49)

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use animations
  without bundling their own copy. ~34KB addition to core.

## §5 Architecture notes

### chatwire-ha plugin (updated Phase 55)

- **Package**: `chatwire-plugins/chatwire-ha/` — `chatwire_ha/__init__.py` + `pyproject.toml`.
- **Class**: `HAIntegration` — `NAME = "chatwire_ha"`, `TIER = "notify"`.
- **Dependency**: `httpx` (declared in pyproject.toml).
- **Lifecycle**: `start(ctx)` → creates `httpx.AsyncClient` with Bearer auth. `stop()` → `aclose()`.
- **Keyword matching**: `text.strip().lower()` → exact lookup in `self._commands` dict.
- **allowed_senders** (new Phase 55): per-command `frozenset` of lowercased handles.
  `on_inbound` checks `msg.handle.lower() in allowed` before firing. Empty set = unrestricted.
- **HA call**: `POST {ha_url}/api/services/{domain}/{service}` with `{"entity_id": ...}`.
- **Reply**: `ctx.send_text(SendTarget(...), f"Done: {description}")`.
- **22 tests** in `tests/test_ha_integration.py`.
- **README**: `docs/plugins/ha.md`.

### chatwire-mqtt plugin (updated Phase 54)

- **Package**: `chatwire-plugins/chatwire-mqtt/` — `chatwire_mqtt/__init__.py` + `pyproject.toml`.
- **Class**: `MQTTIntegration` — `NAME = "chatwire_mqtt"`, `TIER = "official"`.
- **Dependency**: `paho-mqtt>=1.6` (declared in pyproject.toml; guard: `_PAHO_AVAILABLE` flag).
- **Lifecycle**: `start(ctx)` → `tls_set()` (if use_tls) → `connect()` → `loop_start()`. `stop()` → `loop_stop() + disconnect()`.
- **TLS**: `use_tls=true` → `client.tls_set(ca_certs=<path or None>)` before connect.
  `tls_set()` failure → `RuntimeError("TLS setup failed: ...")`.
- **Topic segments**: `_sanitize_topic_segment(s)` replaces `+#/\x00` → `_`; empty → `"_"`.
- **Topic routing**: 1:1 → `<topic>/_15551234567`, group → `<topic>/group/<chat_id>`.
- **Payload schema (v=1)**:
  ```json
  {"v": 1, "rowid": 12345, "handle": "+1...", "text": "...",
   "is_from_me": false, "chat": {"guid": "...", "identifier": "...", "name": null, "is_group": false}}
  ```
- **31 tests** in `tests/test_mqtt_integration.py`; all use `asyncio.run()` to isolate event loop.
- **README**: `docs/plugins/mqtt.md`.

### Plugin registry (chatwire-plugins, updated Phase 53)

- Repo: `github.com/allenbina/chatwire-plugins` — tracks `plugins.json` only.
- 9 entries: apprise, telegram, webhook, stats, theme-rosepine, example, mqtt, ha, xmpp.
- Plugin source dirs live in `chatwire-plugins/chatwire-*/` in chatwire-dev (and public repo).

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

STATE: Phase 55 shipped (chatwire-ha allowed_senders filter + ha.md README).
1090 pytest (1082 pass + 8 pre-existing), 190 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 55 code, healthy).
Public repo allenbina/chatwire: NOT yet synced to Phase 55 (last sync: Phase 54 / 6879d85).

Key blocker for PyPI publish of plugins:
  chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp are NOT on PyPI.
  Marketplace Install button will fail at pip for these until published.
  Requires TWINE_TOKEN env var or ~/.pypirc with PyPI API token.

Pick a task from §4 options:

Option A — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option B — Sync public repo allenbina/chatwire to Phase 55.
  Use rsync method from HANDOFF notes. Remember to restore .gitignore after rsync.

Option C — docs/plugins/xmpp.md README (matches pattern of mqtt.md / ha.md).

Option D — chatwire-mqtt outbound relay (MQTT→iMessage), so automations can send replies.

Option E — #20 Automation engine / #28 trigger grammar (larger, plan first).

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
  curl -s -d "Phase 56 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

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
