#!/usr/bin/env bash
# Verify FDA + Automation grants are correct for the bridge to run under launchd.
# Run on the Mac: bash scripts/check-permissions.sh
#
# Does NOT modify anything. macOS 12+ forbids granting TCC permissions via CLI
# (SIP protects TCC.db, tccutil can only reset). This script identifies what
# the GUI steps should fix.
#
# Override defaults via environment variables:
#   LABEL_PREFIX   default: dev.chatwire
#   INSTALL_DIR    default: $HOME/projects/chatwire
#   PYTHON_VERSION default: 3.14    (used to locate the python.org framework binary)

set -u

LABEL_PREFIX=${LABEL_PREFIX:-dev.chatwire}
INSTALL_DIR=${INSTALL_DIR:-$HOME/projects/chatwire}
PYTHON_VERSION=${PYTHON_VERSION:-3.14}

fail=0
warn=0

log()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=$((fail+1)); }
info() { printf '  \033[33mWARN\033[0m %s\n' "$*"; warn=$((warn+1)); }

TCC_DB=/Library/Application\ Support/com.apple.TCC/TCC.db
VENV_PY=$INSTALL_DIR/.venv/bin/python
CHAT_DB=$HOME/Library/Messages/chat.db
PLIST=$HOME/Library/LaunchAgents/${LABEL_PREFIX}.bridge.plist
CONFIG_FILE=$HOME/.chatwire/config.json
LEGACY_ENV=$HOME/.imessage-tg/.env

# ---------- 1. files present ----------
log "[1/5] files present"
[ -f "$VENV_PY" ] && ok "venv python at $VENV_PY" || bad "missing $VENV_PY (run: python3 -m venv .venv)"
[ -f "$CHAT_DB" ] && ok "chat.db present" || bad "no chat.db — iMessage has never run on this account?"
[ -f "$PLIST" ] && ok "launchd plist installed" || info "plist not installed yet: $PLIST (run: chatwire install-agents)"
if [ -f "$CONFIG_FILE" ]; then
  ok "config.json present"
  perms=$(stat -f "%Lp" "$CONFIG_FILE")
  [ "$perms" = "600" ] && ok "config.json chmod 600" || info "config.json perms are $perms (should be 600): chmod 600 $CONFIG_FILE"
elif [ -f "$LEGACY_ENV" ]; then
  info "legacy .env at $LEGACY_ENV (run: chatwire migrate)"
else
  bad "no config: neither $CONFIG_FILE nor $LEGACY_ENV exist"
fi

# ---------- 2. TCC entries (FDA) ----------
log "[2/5] TCC Full Disk Access entries"
# auth_value: 0 = denied, 2 = allowed (and any row with "Allow Always")
allow_bundle=$(/usr/bin/sqlite3 "$TCC_DB" "SELECT auth_value FROM access WHERE service='kTCCServiceSystemPolicyAllFiles' AND client='org.python.python' LIMIT 1;" 2>/dev/null || echo "")
allow_bin=$(/usr/bin/sqlite3 "$TCC_DB" "SELECT auth_value FROM access WHERE service='kTCCServiceSystemPolicyAllFiles' AND client='/Library/Frameworks/Python.framework/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}' LIMIT 1;" 2>/dev/null || echo "")

case "$allow_bundle" in
  2) ok "org.python.python (Python.app bundle) ALLOWED" ;;
  0) bad "org.python.python (Python.app bundle) DENIED — uncheck+remove in Full Disk Access list" ;;
  "") bad "org.python.python not in FDA — add /Library/Frameworks/Python.framework/Versions/${PYTHON_VERSION}/Resources/Python.app" ;;
  *) info "org.python.python has unexpected auth_value=$allow_bundle" ;;
esac

case "$allow_bin" in
  2) ok "python${PYTHON_VERSION} bin ALLOWED (either this OR the bundle above is enough)" ;;
  0) bad "python${PYTHON_VERSION} bin DENIED — this OVERRIDES the bundle grant. Remove this entry from FDA." ;;
  "") : ;;  # absent is fine if bundle is allowed
  *) info "python${PYTHON_VERSION} bin has unexpected auth_value=$allow_bin" ;;
esac

# ---------- 3. FDA functional test ----------
log "[3/5] chat.db read via venv python"
if [ -x "$VENV_PY" ] && [ -f "$CHAT_DB" ]; then
  out=$("$VENV_PY" -c "
import sqlite3
try:
    with sqlite3.connect('file:$CHAT_DB?mode=ro', uri=True) as c:
        n = c.execute('SELECT COUNT(*) FROM message').fetchone()[0]
    print(f'OK {n}')
except Exception as e:
    print(f'FAIL {type(e).__name__}: {e}')
" 2>&1)
  case "$out" in
    OK\ *) ok "read chat.db: ${out#OK }" ;;
    *) bad "read chat.db via venv python failed (but this test runs from your SSH session which inherits FDA; the real test is the launchd logs): $out" ;;
  esac
else
  info "skipped (missing venv python or chat.db)"
fi

# ---------- 4. Automation test (Messages.app) ----------
log "[4/5] AppleScript -> Messages (Automation grant)"
# A no-op that just opens a connection to Messages. Triggers the Automation prompt
# the first time; succeeds silently once granted.
osa_out=$(osascript -e 'tell application "Messages" to count of services' 2>&1)
case "$osa_out" in
  [0-9]*) ok "Messages.app reachable via osascript ($osa_out services)" ;;
  *"1743"*|*"-1743"*) bad "Automation denied — System Preferences -> Privacy -> Automation, allow Terminal/python -> Messages" ;;
  *) info "unexpected osascript output: $osa_out" ;;
esac

# ---------- 5. launchd status ----------
log "[5/5] launchd status"
state=$(launchctl list | awk -v label="${LABEL_PREFIX}.bridge" '$3 == label {print $1"/"$2}')
if [ -n "$state" ]; then
  pid=${state%/*}
  last=${state#*/}
  if [ "$pid" != "-" ]; then
    ok "agent running pid=$pid last_exit=$last"
  elif [ "$last" = "0" ]; then
    info "agent loaded, not currently running (last_exit=0 — may be between KeepAlive throttles)"
  else
    bad "agent loaded but exited non-zero last_exit=$last — check ~/Library/Logs/chatwire/stderr.log"
  fi
else
  info "agent not loaded: launchctl load -w $PLIST"
fi

log ""
if [ "$fail" -gt 0 ]; then
  log "❌ $fail failure(s), $warn warning(s). Fix failures above and re-run."
  exit 1
elif [ "$warn" -gt 0 ]; then
  log "⚠️  $warn warning(s), no failures."
  exit 0
else
  log "✅ All permission checks passed."
  exit 0
fi
