# Handoff — Phase 17: Ready-to-Build Features + v1.12.0 Release

> Phases 11-16 complete. Plugin sandbox, HSL themes, read state tracking,
> notification depth, contact info, URL slugs, accent picker, PWA icons,
> custom CSS scoping — all shipped. 132 tests green.

## 1. State

- **mbair**: v1.11.0 + all Phase 11-16 features deployed.
- **Tests**: 132 Vitest, 15 E2E, 615 pytest. All green.
- **Theme system**: HSL-native, 22 theme blocks in built CSS, no purging.

## 2. Chunks

### Chunk 1: Scoped API keys (#26)

Multiple named API keys with per-key permission scoping.

1. **Create `web/api_keys.py`**:
   - `APIKey` dataclass: `name: str`, `key_hash: str`, `scopes: list[str]`, `created_at: str`
   - Scopes: `"trigger_actions"`, `"read_conversations"`, `"send_messages"`, `"manage_settings"`
   - `generate_key()` → returns `cwk_` + 32 random hex chars
   - `hash_key(key)` → PBKDF2-SHA256 (same as password hashing)
   - `verify_key(key, key_hash)` → bool
   - `load_keys()` / `save_keys()` → read/write `~/.chatwire/api_keys.json`
   - `check_scope(key_hash, required_scope)` → bool

2. **Add auth middleware** in `web/auth.py`:
   - Check `Authorization: Bearer cwk_...` header
   - If present: validate key, check scope for the requested route
   - Route → scope mapping:
     - `POST /api/v1/actions/*` → `trigger_actions`
     - `GET /api/v1/conversations`, `GET /api/v1/messages` → `read_conversations`
     - `POST /api/v1/send`, `POST /send` → `send_messages`
     - `POST /api/ui/settings/*` → `manage_settings`
   - If wrong scope → 403
   - Cookie auth still works for web UI (no change)

3. **Settings UI** in `SettingsPage.tsx`:
   - New "API Keys" accordion section
   - Table: Name | Key (masked, copy button) | Scopes (checkboxes) | Delete
   - "+ Add Key" button → generates key, shows it ONCE, user copies it
   - Scopes: 4 checkboxes, all checked by default
   - API endpoints: `GET/POST/DELETE /api/ui/api-keys`

4. Run tests. Commit. Push.

### Chunk 2: Clear all notifications / mark all read (#19)

1. **Backend**: `POST /api/ui/read-state/all` already exists from Phase 11.
   Verify it works — should mark all conversations as seen.

2. **Frontend**: Add "Mark all read" button in sidebar:
   - Small button/icon at top of conversation list (next to where header was)
   - Calls `POST /api/ui/read-state/all`
   - Clears all unread badges immediately (optimistic update)
   - Also calls `navigator.clearAppBadge()` if available
   - Keyboard shortcut: `Shift+Escape`

3. Add Vitest test for the button.
4. Run tests. Commit. Push.

### Chunk 3: Settings appearance revamp (#9)

1. **Theme picker**: dropdown/select with 3 structural themes (default/compact/flat)
   - Shows current selection
   - Changing updates `data-style` attribute live

2. **Color scheme picker**: dropdown/select with 21 color schemes
   - Shows current selection
   - Changing updates `data-theme` attribute live

3. **Custom accent**: already shipped (hex input + swatch + native picker)
   - Verify it works with HSL scheme system

4. **Global CSS override**: single textarea
   - Already exists — verify it's in the right section
   - NOT per-theme (deferred to Discord feedback)

5. Run tests. Commit. Push.

### Chunk 4: Sidebar footer quick-access (#10)

1. Bottom of sidebar already has "Settings" link
2. Add "Appearance" quick-link next to it
   - Navigates to `/settings` and scrolls to Appearance section
   - Or: small theme/scheme dropdown right in the footer (pick live)
3. Keep it minimal — don't clutter the footer.
4. Run tests. Commit. Push.

### Chunk 5: v1.12.0 release (#29)

Ship everything to the public repo and PyPI.

1. **Bump version**: update `_version.py` to `1.12.0`
2. **Update CHANGELOG.md**: add [1.12.0] section with all Phase 11-17 features
3. **Sync to public repo**:
   ```bash
   cd ~/git/chatwire
   # Remove old files, rsync from chatwire-dev
   git rm -rf . 2>/dev/null || true
   rsync -av --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
     ~/git/chatwire-dev/ ~/git/chatwire/
   git add -A
   git commit -m "feat: sync Phase 11-17 — plugin sandbox, HSL themes, read state, scoped API keys, v1.12.0"
   git push
   ```
4. **Tag and push**: `git tag v1.12.0 && git push --tags`
   - Triggers: PyPI publish, GitHub Release, Docker GHCR, Homebrew tap bump
5. **Deploy to mbair** (once PyPI has 1.12.0):
   ```bash
   ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir chatwire==1.12.0"
   ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.bridge && \
     /bin/launchctl kickstart -k gui/501/dev.chatwire.web && \
     /bin/launchctl kickstart -k gui/501/dev.chatwire.keepawake"
   ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"
   ```
6. **Notify**:
   ```bash
   curl -s -d "v1.12.0 released — plugin sandbox, HSL themes, scoped API keys, read state tracking" ntfy.sh/p9SKpYzY70LlyK1N
   ```

## 3. Follow-ups (not in this phase)

- #20 Automation engine (needs action tier)
- #28 Trigger grammar (depends on #20)
- #27 MQTT output (depends on #20)
- #23 Data exposure warning (depends on #20)
- #14 Theme plugin registration
- #21, #22 Documentation
- #24 Discord server
- #25 Uninstaller testing
- #1 Mac DMG (Apple Dev account)
- #2 Custom marketplaces (deferred)

## 6. Next prompt

```
Read docs/HANDOFF.md in full. This is your state file.

STATE: Phase 17 — Ready-to-Build Features + v1.12.0 Release.
  132 Vitest, 15 E2E, 615 pytest — all green.
  HSL themes live. Plugin sandbox live. Read state live.

PRIORITY: Chunk 1 — Scoped API keys.

STEP 1: Create web/api_keys.py
  See §2 Chunk 1 step 1 for full spec.
  Use PBKDF2-SHA256 for key hashing (same as password in auth.py).
  Key format: cwk_ + 32 random hex chars.
  Storage: ~/.chatwire/api_keys.json

STEP 2: Update web/auth.py
  Add Bearer token auth path alongside cookie auth.
  Route → scope mapping per §2 Chunk 1 step 2.

STEP 3: Settings UI — API Keys accordion
  Table with name, masked key, scope checkboxes, delete button.
  "+ Add Key" generates and shows key once.
  API: GET/POST/DELETE /api/ui/api-keys

STEP 4: Tests + commit + push.

Then continue to Chunks 2-5 in order. Read each chunk's spec before starting.

IMPORTANT — Chunk 5 is the v1.12.0 release. Follow the exact steps in
§2 Chunk 5. Bump version, update changelog, sync to public repo, tag,
push tag, wait for PyPI, deploy to mbair via pip install.

After EACH chunk — commit, push, and notify:
  curl -s -d "Phase 17 Chunk N complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

The loop script auto-deploys frontend dist to mbair after each session.
For Chunk 5 (v1.12.0), also do the full pip install deploy per the spec.
```
