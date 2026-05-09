#!/usr/bin/env bash
# Curl-pipe-bash installer for chatwire.
#
# One-liner (latest main):
#   curl -fsSL https://raw.githubusercontent.com/allenbina/chatwire/main/scripts/install.sh | bash
#
# Pin to a tag:
#   CHATWIRE_REF=v0.1.0 bash -c "$(curl -fsSL https://raw.githubusercontent.com/allenbina/chatwire/main/scripts/install.sh)"
#
# IMPORTANT: pipe into `bash`, not `sh`. macOS `/bin/sh` is bash 3.2 in POSIX
# mode, which silently ignores `set -o pipefail` — a curl 404 would feed an
# empty stream into tar and the script would proceed thinking it succeeded.
#
# Override-able env vars:
#   CHATWIRE_REPO        owner/repo on GitHub  (default: allenbina/chatwire)
#   CHATWIRE_REF         git ref / tag         (default: main)
#   CHATWIRE_INSTALL_DIR install location      (default: ~/.local/share/chatwire)
#   CHATWIRE_BIN_DIR     wrapper bin location  (default: ~/.local/bin)
#   CHATWIRE_PYTHON      python interpreter    (default: python3)
#
# This script does not load launchd or grant TCC permissions — you'll run
#   chatwire install-agents
#   chatwire setup
# yourself afterwards. See README.md for why.

set -euo pipefail

REPO="${CHATWIRE_REPO:-allenbina/chatwire}"
REF="${CHATWIRE_REF:-main}"
INSTALL_DIR="${CHATWIRE_INSTALL_DIR:-$HOME/.local/share/chatwire}"
BIN_DIR="${CHATWIRE_BIN_DIR:-$HOME/.local/bin}"
PYTHON="${CHATWIRE_PYTHON:-python3}"

# ---------- guard against unsafe paths ----------

# A single empty/short INSTALL_DIR + a later `rm -rf` is how installers
# delete entire homedirs. Validate before any destructive op.

# 1. Strip trailing slashes for canonical comparisons.
INSTALL_DIR="${INSTALL_DIR%/}"
HOME_CANON="${HOME%/}"

# 2. Must be non-empty and absolute.
if [ -z "$INSTALL_DIR" ]; then
  echo "CHATWIRE_INSTALL_DIR is empty." >&2
  exit 1
fi
case "$INSTALL_DIR" in
  /*) ;;
  *) echo "CHATWIRE_INSTALL_DIR must be absolute (got '$INSTALL_DIR')." >&2; exit 1 ;;
esac

# 3. Reject shell-special chars — the wrapper heredoc later interpolates
# $INSTALL_DIR literally, and ", \, $, ` would break the generated script.
case "$INSTALL_DIR" in
  *[\"\`\$\\]*)
    echo "CHATWIRE_INSTALL_DIR contains shell-special characters (\" \$ \` \\)." >&2
    echo "Refusing to install to a path that would break the wrapper script." >&2
    exit 1
    ;;
esac

# 4. Allowlist: must be a strict descendant of \$HOME. This is the real
# safety net — catches /, $HOME (no subdir), $HOME with trailing slash,
# and every system path enumeration would ever miss. Override with
# CHATWIRE_ALLOW_OUTSIDE_HOME=1 if you really mean it.
case "$INSTALL_DIR" in
  "$HOME_CANON"/?*) ;;
  *)
    if [ "${CHATWIRE_ALLOW_OUTSIDE_HOME:-0}" != "1" ]; then
      echo "INSTALL_DIR ($INSTALL_DIR) is not under \$HOME ($HOME_CANON)." >&2
      echo "Set CHATWIRE_ALLOW_OUTSIDE_HOME=1 to override (you accept the risk)." >&2
      exit 1
    fi
    # Even with override, refuse obvious system paths.
    case "$INSTALL_DIR" in
      /|/usr|/usr/*|/etc|/etc/*|/var|/var/*|/bin|/bin/*|/sbin|/sbin/*|\
/Applications|/Applications/*|/System|/System/*|/Library|/Library/*|\
/private/*|/opt|/tmp|/Users)
        echo "Refusing to install to '$INSTALL_DIR' (system path)." >&2
        exit 1
        ;;
    esac
    ;;
esac

# ---------- platform checks ----------

if [ "$(uname -s)" != "Darwin" ]; then
  echo "chatwire runs on macOS only (the bridge needs chat.db + AppleScript)." >&2
  exit 1
fi

ver=$(sw_vers -productVersion)
major="${ver%%.*}"
case "$major" in
  ''|*[!0-9]*)
    echo "Could not parse macOS version from sw_vers ('$ver'). Aborting." >&2
    exit 1
    ;;
esac
if [ "$major" -lt 11 ]; then
  echo "macOS 11+ required (you have $ver). Aborting." >&2
  exit 1
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 not found ($PYTHON in PATH). Install python.org's Python 3.11+." >&2
  echo "https://www.python.org/downloads/macos/" >&2
  exit 1
fi

# Resolve PYTHON to its real path before invoking it. Catches the Xcode CLT
# stub at /usr/bin/python3, which on a fresh Mac (no CLT installed) pops a
# GUI prompt the moment you run it. Refuse rather than ambush the user.
py_resolved=$(command -v "$PYTHON")
case "$py_resolved" in
  /usr/bin/python3|/usr/bin/python)
    echo "$PYTHON resolves to $py_resolved (Xcode Command Line Tools stub)." >&2
    echo "On a Mac without CLT installed, invoking it triggers a GUI prompt;" >&2
    echo "even when CLT is installed, TCC treats it differently from python.org Python." >&2
    echo "Install python.org's Python 3.11+ (https://www.python.org/downloads/macos/)" >&2
    echo "or set CHATWIRE_PYTHON to a python.org binary explicitly." >&2
    exit 1
    ;;
esac

py_version=$("$PYTHON" -c 'import sys; print(sys.version_info.major, sys.version_info.minor)' 2>/dev/null || true)
py_major="${py_version%% *}"
py_minor="${py_version##* }"
case "$py_major" in
  ''|*[!0-9]*) echo "Could not determine Python version from $PYTHON." >&2; exit 1 ;;
esac
case "$py_minor" in
  ''|*[!0-9]*) echo "Could not determine Python version from $PYTHON." >&2; exit 1 ;;
esac
if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 11 ]; }; then
  echo "Python >= 3.11 required (you have $py_major.$py_minor)." >&2
  exit 1
fi

py_path=$("$PYTHON" -c 'import sys; print(sys.executable)')
echo "→ Python: $py_path ($py_major.$py_minor)"

# Inverted detection: warn unless Python lives under a known
# Python.framework install path. Catches Homebrew, pyenv, asdf, conda,
# miniconda — all of which have the same TCC-identity problem
# (FDA/Automation granted to one binary doesn't carry over to the others).
case "$py_path" in
  /Library/Frameworks/Python.framework/*) ;;          # python.org — preferred
  /opt/local/Library/Frameworks/Python.framework/*) ;; # MacPorts equivalent
  *)
    echo "WARNING: $py_path is not python.org's Python." >&2
    echo "macOS TCC tracks each Python binary as a separate identity, so" >&2
    echo "FDA + Automation grants given to (e.g.) python.org won't apply here." >&2
    echo "python.org's installer is strongly recommended; see docs/REFERENCE_INSTALL.md." >&2
    if [ -e /dev/tty ]; then
      printf "Continue anyway? [y/N] " >&2
      read -r ans </dev/tty || ans=""
      case "$ans" in y|Y|yes|YES|Yes) ;; *) exit 1 ;; esac
    else
      echo "(non-interactive shell; refusing to continue without confirmation —" >&2
      echo " re-run interactively or set CHATWIRE_PYTHON to a python.org binary)" >&2
      exit 1
    fi
    ;;
esac

# ---------- cleanup state ----------

tmpdir=$(mktemp -d)
venv_just_created=0

cleanup() {
  rc=$?
  rm -rf "$tmpdir"
  # If we created the venv this run AND we're exiting non-zero, blow it
  # away so a retry doesn't reuse a half-built venv (the existence check
  # at venv-creation time would otherwise skip the recreate).
  if [ "$rc" -ne 0 ] && [ "$venv_just_created" = "1" ] && [ -d "$INSTALL_DIR/.venv" ]; then
    echo "→ Cleaning up partially-built venv at $INSTALL_DIR/.venv" >&2
    rm -rf "$INSTALL_DIR/.venv"
  fi
}
trap cleanup EXIT INT TERM

# ---------- download ----------

tarball_url="https://codeload.github.com/$REPO/tar.gz/$REF"
echo "→ Tarball: $tarball_url"

# Two-step: download to a file, check curl's exit, then extract. Belt &
# suspenders for the case where someone runs this under `sh` despite the
# warning above (pipefail no-op, would otherwise mask a curl failure).
if ! curl -fsSL "$tarball_url" -o "$tmpdir/src.tar.gz"; then
  echo "Failed to fetch $tarball_url." >&2
  echo "Check CHATWIRE_REPO / CHATWIRE_REF — and that the ref exists on GitHub." >&2
  exit 1
fi
if ! tar -xzf "$tmpdir/src.tar.gz" -C "$tmpdir"; then
  echo "Tarball at $tarball_url extracted with errors." >&2
  exit 1
fi

# `find ... -print -quit` instead of `find ... | head -n 1` — head closes
# the pipe early, find dies of SIGPIPE, pipefail propagates the failure.
src=$(find "$tmpdir" -mindepth 1 -maxdepth 1 -type d -print -quit)
if [ -z "$src" ] || [ ! -f "$src/chatwire_cli.py" ]; then
  echo "Tarball extracted but doesn't look like the repo (no chatwire_cli.py at top level)." >&2
  exit 1
fi

# ---------- install ----------

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
echo "→ Installing to $INSTALL_DIR"

# rsync if available (preserves a pre-existing .venv on upgrades), otherwise
# fall back to a wipe-and-copy that preserves the venv across the wipe.
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '.venv/' --exclude '__pycache__/' "$src/" "$INSTALL_DIR/"
else
  if [ -d "$INSTALL_DIR/.venv" ]; then
    mv "$INSTALL_DIR/.venv" "$tmpdir/.venv-keep"
  fi
  # INSTALL_DIR validated absolute & non-dangerous up top; safe to wipe.
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  cp -R "$src/." "$INSTALL_DIR/"
  if [ -d "$tmpdir/.venv-keep" ]; then
    mv "$tmpdir/.venv-keep" "$INSTALL_DIR/.venv"
  fi
fi

# ---------- venv ----------

if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
  echo "→ Creating virtualenv"
  "$PYTHON" -m venv "$INSTALL_DIR/.venv"
  venv_just_created=1
fi

echo "→ Installing dependencies"
# `pip install .` reads pyproject.toml as the single source of truth for
# dependencies and registers the entry point in the venv. If pip fails, the
# cleanup trap removes the half-built venv (only on fresh creates — preserves
# a working venv across upgrade reruns).
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install "$INSTALL_DIR"

# ---------- wrapper ----------

cat > "$BIN_DIR/chatwire" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/chatwire_cli.py" "\$@"
EOF
chmod +x "$BIN_DIR/chatwire"

# ---------- done ----------

# `case` instead of `grep` so a $BIN_DIR with regex metacharacters can't
# break the PATH check.
on_path=0
case ":$PATH:" in
  *":$BIN_DIR:"*) on_path=1 ;;
esac
if [ "$on_path" = "0" ]; then
  echo
  echo "⚠  $BIN_DIR is not on your PATH. Add this to ~/.zshrc (or ~/.bashrc):"
  echo "      export PATH=\"$BIN_DIR:\$PATH\""
  echo "  (Default macOS shell is zsh; .zshrc is read for interactive shells.)"
fi

cat <<EOF

✓ Installed chatwire to $INSTALL_DIR
  CLI:  $BIN_DIR/chatwire

Next steps:
  1. $BIN_DIR/chatwire install-agents   # render + load launchd plists
  2. $BIN_DIR/chatwire setup            # opens the web wizard at http://localhost:8723/setup
  3. $BIN_DIR/chatwire doctor           # verify FDA + Automation grants

To upgrade later, re-run this same one-liner.
Docs: https://github.com/$REPO
EOF
