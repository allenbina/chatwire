#!/usr/bin/env bash
# chain-waves.sh — wait for each wave's loop to finish, copy next HANDOFF,
# and relaunch. Runs waves 2→3→4→5 fully autonomously.
#
# Pre-staged HANDOFFs: docs/HANDOFF-wave3.md, docs/HANDOFF-wave4.md,
# docs/HANDOFF-wave5.md. Each gets copied to docs/HANDOFF.md when its
# turn comes.
#
# Usage:
#   scripts/chain-waves.sh        # start watching (run in tmux)

set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/bin:$PATH"

REPO="/home/mediafront/git/chatwire"
HANDOFF="$REPO/docs/HANDOFF.md"
LOOP="$REPO/scripts/chatwire-loop.sh"
NTFY_TOPIC="p9SKpYzY70LlyK1N"

ntfy() {
    local title="$1" priority="${2:-default}" body="${3:-}"
    curl -fsS -H "Title: $title" -H "Priority: $priority" \
        -d "$body" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
}

wait_for_loop() {
    echo "$(date -Iseconds) Waiting for chatwire-loop session to finish..."
    while tmux has-session -t chatwire-loop 2>/dev/null; do
        sleep 30
    done
    echo "$(date -Iseconds) Loop session ended."
}

stage_handoff() {
    local wave="$1"
    local src="$REPO/docs/HANDOFF-wave${wave}.md"
    if [[ ! -f "$src" ]]; then
        echo "ERROR: $src not found!" >&2
        ntfy "chain-waves FAILED" "max" "Missing HANDOFF-wave${wave}.md"
        exit 1
    fi
    cd "$REPO"
    git pull --ff-only
    cp "$src" "$HANDOFF"
    git add docs/HANDOFF.md
    git commit -m "$(cat <<EOF
docs: stage HANDOFF.md for wave $wave

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
    git push origin main
    echo "$(date -Iseconds) Staged HANDOFF for wave $wave"
}

run_wave() {
    local wave="$1" iterations="$2"
    echo "$(date -Iseconds) === Starting wave $wave ($iterations chunks) ==="
    ntfy "Wave $wave starting" "default" "$iterations chunks queued"

    tmux new-session -d -s chatwire-loop \
        "cd $REPO && $LOOP --max-iterations $iterations --session-timeout 20 --model sonnet 2>&1 | tee -a $HOME/.local/state/chatwire-loop/logs/wave${wave}-$(date +%Y%m%d-%H%M%S).log"

    wait_for_loop

    echo "$(date -Iseconds) === Wave $wave complete ==="
    ntfy "Wave $wave complete" "low" "All $iterations chunks done. $(cd $REPO && git log --oneline -1)"
}

# ---------------------------------------------------------------
# Main: wait for wave 2 (already running), then chain 3 → 4 → 5
# ---------------------------------------------------------------

echo "$(date -Iseconds) chain-waves.sh started. Watching for wave 2 completion."

# --- Wait for wave 2 to finish ---
wait_for_loop
ntfy "Wave 2 complete — chaining to wave 3" "default"

# --- Wave 3: 12 chunks ---
stage_handoff 3
run_wave 3 12

# --- Wave 4: 6 chunks ---
stage_handoff 4
run_wave 4 6

# --- Wave 5: 3 chunks ---
stage_handoff 5
run_wave 5 3

echo "$(date -Iseconds) === ALL WAVES COMPLETE ==="
ntfy "All waves complete! (2-5)" "high" "Full chatwire roadmap shipped. Time for a beer."
