# Install & Build Testing

Tracks prerequisites, test scripts, and verification steps for each install method.

---

## Prerequisites by machine

### mbair (macOS 12.7.6, x86_64 — production + test host)

| Tool | Status | Install command |
|------|--------|----------------|
| Python 3.14 | Installed | (python.org framework build) |
| pipx | Installed | `brew install pipx` |
| uv 0.11.14 | **Installed 2026-05-16** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Homebrew | Installed | (slow on macOS 12 — compiles from source, no bottles) |
| Rust/cargo | **NOT installed** | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Tauri CLI | **NOT installed** | `cargo install tauri-cli` (requires Rust, compiles ~30min+) |
| Xcode CLT | Installed | (needed for AppleScript/TCC) |

### plinux (Ubuntu 20.04, x86_64 — dev host, Python 3.8)

| Tool | Status | Notes |
|------|--------|-------|
| Python 3.8 | Installed | Too old for chatwire core (needs 3.10+) |
| Can run tests | Yes | pytest mocks around macOS-specific code |
| Can build frontend | Yes | node/npm available |
| Cannot test installs | — | Not macOS, no chat.db |

---

## Test scripts per install method

### pip / pipx (works today)

```bash
# Fresh install
pipx install chatwire
chatwire doctor
chatwire --version

# Upgrade
pipx upgrade chatwire
chatwire --version  # verify new version

# Uninstall
chatwire uninstall --purge --dry-run  # preview
chatwire uninstall-agents
pipx uninstall chatwire
```

### uv (needs verification)

```bash
# Ensure uv is on PATH
source ~/.local/bin/env

# Fresh install
uv tool install chatwire
chatwire doctor
chatwire --version

# With MCP support
uv tool install 'chatwire[mcp]'

# Upgrade
uv tool upgrade chatwire
chatwire --version

# Uninstall
chatwire uninstall-agents
uv tool uninstall chatwire
```

### Homebrew (needs formula)

```bash
# Add tap (once we have one)
brew tap allenbina/chatwire

# Install
brew install chatwire
chatwire doctor

# Upgrade
brew upgrade chatwire

# Uninstall
chatwire uninstall-agents
brew uninstall chatwire
chatwire uninstall --purge  # remove config/data
```

**Formula location:** `github.com/allenbina/homebrew-chatwire/Formula/chatwire.rb`

**Bottle concern:** macOS 12 (Monterey) may not get pre-built bottles from Homebrew.
Users on macOS 12 will compile from source (slow). macOS 13+ should get bottles.

### DMG / Tauri (post-RC1)

```bash
# Prerequisites (one-time on build machine)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install tauri-cli

# Build
cd packages/tauri  # (doesn't exist yet)
cargo tauri build

# Output: target/release/bundle/dmg/Chatwire_x.y.z.dmg
# Test: open DMG, drag to /Applications, launch, verify menu bar icon
```

**Gatekeeper bypass (unsigned):**
```bash
# If macOS blocks the app:
xattr -cr /Applications/Chatwire.app
# Or: right-click → Open → click "Open" in dialog
```

---

## Verification checklist (all methods)

After any install:

- [ ] `chatwire --version` prints correct version
- [ ] `chatwire doctor` passes (macOS, Python, FDA, Automation)
- [ ] `chatwire init` runs wizard (or detects existing config)
- [ ] `chatwire install-agents` renders plists + loads agents
- [ ] Web UI accessible at http://localhost:8723
- [ ] `/healthz` returns ok
- [ ] Amphetamine note printed during install-agents

After upgrade:

- [ ] Config preserved (`~/.chatwire/config.json` unchanged)
- [ ] Services restart cleanly (launchd KeepAlive handles this)
- [ ] Web UI loads new version (check version in /healthz response)
- [ ] No duplicate installations on PATH

After uninstall:

- [ ] `chatwire` command no longer on PATH
- [ ] LaunchAgents removed from ~/Library/LaunchAgents/
- [ ] `--purge`: config.json, plugins/, state files, logs all removed
- [ ] `--purge --dry-run`: shows what WOULD be removed, changes nothing

---

## macOS version compatibility

| macOS | Python 3.10+ available? | Homebrew bottles? | Tauri support? | Notes |
|-------|------------------------|-------------------|----------------|-------|
| 12 (Monterey) | Yes (python.org) | Unlikely (EOL) | Yes | mbair runs this. Brew compiles from source. |
| 13 (Ventura) | Yes | Yes | Yes | Minimum for most users |
| 14 (Sonoma) | Yes | Yes | Yes | Current -1 |
| 15 (Sequoia) | Yes | Yes | Yes | Current. `launchctl load -w` deprecated but works. |

**Recommendation:** Support macOS 12+ but document that brew is slow on 12.
Target macOS 13+ for "recommended" install experience.

---

## What still needs doing

- [ ] Verify `uv tool install chatwire` works end-to-end on mbair
- [ ] Write Homebrew formula + create tap repo
- [ ] Test brew install on macOS 13+ (borrow a machine or VM?)
- [ ] Install Rust on mbair (when ready for Tauri work)
- [ ] Create `packages/tauri/` scaffold
- [ ] Design app icon (needed before any native packaging)
- [ ] Test `chatwire[mcp]` extra installs correctly via uv and pip
