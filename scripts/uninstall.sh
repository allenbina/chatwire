#!/usr/bin/env bash
# chatwire uninstall script
# Stops launchd agents, removes plists, uninstalls the package, and deletes
# all chatwire-owned data directories.
#
# Usage:  bash scripts/uninstall.sh [--dry-run]
#
# --dry-run   Print every action that WOULD be taken; touch nothing.
#
# This script is intentionally safe: every destructive step checks for file
# existence first, and the confirmation gate prevents accidents.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LABEL_PREFIX="dev.chatwire"
SERVICES=(bridge web keepawake)

CHATWIRE_DIR="${HOME}/.chatwire"
LOG_DIR="${HOME}/Library/Logs/chatwire"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RED='\033[0;31m'
YEL='\033[0;33m'
GRN='\033[0;32m'
RST='\033[0m'

_step()  { echo -e "${GRN}==> ${*}${RST}"; }
_warn()  { echo -e "${YEL}    ${*}${RST}"; }
_info()  { echo -e "    ${*}"; }
_error() { echo -e "${RED}ERROR: ${*}${RST}" >&2; }

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    echo -e "${YEL}[DRY RUN] No changes will be made.${RST}"
    echo ""
fi

_run() {
    # _run cmd arg arg ...  — execute or print, depending on DRY_RUN
    if [[ "$DRY_RUN" -eq 1 ]]; then
        _info "(dry-run) $*"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# Confirmation gate (skipped in dry-run so CI/tests can call without stdin)
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" -eq 0 ]]; then
    echo ""
    echo -e "${RED}WARNING: This will permanently remove chatwire and all its data.${RST}"
    echo ""
    echo "The following will be deleted:"
    echo "  • launchd agents (bridge, web, keepawake)"
    echo "  • plist files in ${LAUNCH_AGENTS_DIR}/dev.chatwire.*"
    echo "  • the chatwire Python package (via pipx)"
    echo "  • ${CHATWIRE_DIR}/"
    echo "  • ${LOG_DIR}/"
    echo ""
    read -r -p "Type YES to continue: " confirm
    if [[ "$confirm" != "YES" ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 1: Stop launchd agents
# ---------------------------------------------------------------------------

_step "Step 1: Stopping launchd agents"

for svc in "${SERVICES[@]}"; do
    label="${LABEL_PREFIX}.${svc}"
    target="gui/$(id -u)/${label}"
    if command -v launchctl &>/dev/null; then
        _info "launchctl bootout ${target}"
        if [[ "$DRY_RUN" -eq 0 ]]; then
            launchctl bootout "${target}" 2>/dev/null || true
        fi
    else
        _warn "launchctl not found — skipping (not macOS?)"
        break
    fi
done

# ---------------------------------------------------------------------------
# Step 2: Remove plist files
# ---------------------------------------------------------------------------

_step "Step 2: Removing plist files"

for svc in "${SERVICES[@]}"; do
    plist="${LAUNCH_AGENTS_DIR}/${LABEL_PREFIX}.${svc}.plist"
    if [[ -f "$plist" ]]; then
        _run rm -f "$plist"
        _info "removed ${plist}"
    else
        _info "not found (skip): ${plist}"
    fi
done

# ---------------------------------------------------------------------------
# Step 3: Uninstall chatwire Python package
# ---------------------------------------------------------------------------

_step "Step 3: Uninstalling chatwire via pipx"

if command -v pipx &>/dev/null; then
    _run pipx uninstall chatwire
elif [[ -x "${HOME}/.local/bin/pipx" ]]; then
    _run "${HOME}/.local/bin/pipx" uninstall chatwire
else
    _warn "pipx not found — skipping package removal"
    _warn "If chatwire was installed another way, remove it manually."
fi

# ---------------------------------------------------------------------------
# Step 4: Remove ~/.chatwire/
# ---------------------------------------------------------------------------

_step "Step 4: Removing ${CHATWIRE_DIR}/"

if [[ -d "$CHATWIRE_DIR" ]]; then
    _run rm -rf "$CHATWIRE_DIR"
    _info "removed ${CHATWIRE_DIR}"
else
    _info "not found (skip): ${CHATWIRE_DIR}"
fi

# ---------------------------------------------------------------------------
# Step 5: Remove ~/Library/Logs/chatwire/
# ---------------------------------------------------------------------------

_step "Step 5: Removing ${LOG_DIR}/"

if [[ -d "$LOG_DIR" ]]; then
    _run rm -rf "$LOG_DIR"
    _info "removed ${LOG_DIR}"
else
    _info "not found (skip): ${LOG_DIR}"
fi

# ---------------------------------------------------------------------------
# Step 6: Thumbnail cache (already inside ~/.chatwire/ but listed explicitly)
# ---------------------------------------------------------------------------

_step "Step 6: Thumbnail cache"

THUMB_DIR="${CHATWIRE_DIR}/thumb_cache"
if [[ "$DRY_RUN" -eq 1 ]]; then
    _info "(dry-run) would remove ${THUMB_DIR}/ (covered by step 4)"
else
    _info "covered by step 4 (${THUMB_DIR} removed with parent)"
fi

# ---------------------------------------------------------------------------
# Report: what chatwire CANNOT remove
# ---------------------------------------------------------------------------

echo ""
echo "==========================================================="
echo " What chatwire CANNOT remove on your behalf:"
echo "==========================================================="
echo ""
echo "  ~/Library/Messages/      — Apple's database (we never write to it)"
echo ""
echo "  Homebrew tap:"
echo "    brew untap allenbina/homebrew-tap"
echo ""
echo "  Browser saved passwords / cookies — managed by your browser"
echo ""

# List any installed chatwire plugins (entry-point packages)
echo "  Third-party plugin packages:"
PLUGINS=()
if command -v pipx &>/dev/null; then
    # Already uninstalled, so list before uninstall is the right time; but in
    # case someone re-runs after, probe the venv directly if still present.
    :
fi

# Try to find injected packages from the pipx venv metadata (best-effort)
PIPX_HOME="${PIPX_HOME:-${HOME}/.local/pipx}"
VENV_META="${PIPX_HOME}/venvs/chatwire/pipx_metadata.json"
if command -v python3 &>/dev/null && [[ -f "$VENV_META" ]]; then
    mapfile -t PLUGINS < <(
        python3 -c "
import json, sys
try:
    d = json.load(open('${VENV_META}'))
    for k in d.get('injected_packages', {}).keys():
        print(k)
except Exception as e:
    pass
" 2>/dev/null
    )
fi

if [[ "${#PLUGINS[@]}" -gt 0 ]]; then
    echo "    The following plugins were injected into the chatwire venv."
    echo "    They are removed along with the venv by pipx (step 3 above),"
    echo "    but if you want them elsewhere, reinstall them separately:"
    for pkg in "${PLUGINS[@]}"; do
        echo "      pipx uninject chatwire ${pkg}"
    done
else
    echo "    No injected plugins detected (or venv already removed)."
    echo "    If you had plugins, they were removed with the venv in step 3."
fi

echo ""
echo "==========================================================="
echo ""

if [[ "$DRY_RUN" -eq 0 ]]; then
    echo -e "${GRN}chatwire uninstall complete.${RST}"
fi
