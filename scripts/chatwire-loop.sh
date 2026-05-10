#!/usr/bin/env bash
# chatwire-loop.sh — chained headless claude sessions for chatwire dev.
#
# Reads HANDOFF.md §6 as the seed prompt, runs `claude -p`, then checks
# whether HANDOFF.md was rewritten with a new §6. If so, commits and
# loops with the fresh prompt. Stops when §6 is unchanged, the iteration
# cap is reached, or claude exits non-zero.
#
# After each iteration cap (--max-iterations), sends an ntfy notification
# with confidence levels and action buttons. User taps "Continue" or
# "Stop" from their phone. If no response within the timeout (or during
# sleep hours), the loop waits until the user responds.
#
# Usage:
#   scripts/chatwire-loop.sh                         # defaults
#   scripts/chatwire-loop.sh --max-iterations 5      # cap at 5 sessions
#   scripts/chatwire-loop.sh --model opus             # model override
#   scripts/chatwire-loop.sh --budget-usd 20          # per-session cap
#   scripts/chatwire-loop.sh --phases 8               # run up to N approval cycles
#   scripts/chatwire-loop.sh --dry-run                # show prompt, don't fire

set -euo pipefail

# --- PATH bootstrap (cron's PATH is bare) ---
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/bin:$PATH"

# --- NVM bootstrap (for npm commands in headless mode) ---
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# --- Force subscription auth: never API key ---
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    _ANTHROPIC_API_KEY_WAS_SET=1
    unset ANTHROPIC_API_KEY
fi
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BEDROCK_BASE_URL ANTHROPIC_VERTEX_PROJECT_ID 2>/dev/null || true

# --- Resolve paths ---
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HANDOFF="$REPO_DIR/docs/HANDOFF.md"
LOGS_DIR="${CHATWIRE_LOGS_DIR:-$HOME/.local/state/chatwire-loop/logs}"
mkdir -p "$LOGS_DIR"

# --- Defaults ---
MODEL="sonnet"
FALLBACK_MODEL="claude-opus-4-7"
BUDGET_USD=""
MAX_ITERATIONS=10
MAX_PHASES=99            # how many approval cycles before hard stop
SESSION_TIMEOUT_M=15     # kill session after N minutes; 0 = no timeout
NTFY_TOPIC="p9SKpYzY70LlyK1N"
APPROVAL_TIMEOUT_S=14400 # 4 hours to respond during awake hours
SLEEP_START=25           # disabled — always send notifications
SLEEP_END=0              # disabled — user's phone handles DND
DRY_RUN=0

# --- Args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)           MODEL="$2"; shift 2 ;;
        --fallback-model)  FALLBACK_MODEL="$2"; shift 2 ;;
        --budget-usd)      BUDGET_USD="$2"; shift 2 ;;
        --max-iterations)  MAX_ITERATIONS="$2"; shift 2 ;;
        --max-phases)      MAX_PHASES="$2"; shift 2 ;;
        --session-timeout) SESSION_TIMEOUT_M="$2"; shift 2 ;;
        --ntfy-topic)      NTFY_TOPIC="$2"; shift 2 ;;
        --dry-run)         DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,6p' "$0"
            echo
            echo "Usage: $0 [--model NAME] [--budget-usd N] [--max-iterations N] [--max-phases N] [--session-timeout M] [--ntfy-topic TOPIC] [--dry-run]"
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# --- Ntfy helpers ---
ntfy_send() {
    local title="$1" priority="${2:-default}" body="${3:-}"
    [[ "${#body}" -gt 4000 ]] && body="${body:0:4000}"$'\n...(truncated)'
    curl -fsS -X POST \
        -H "Title: $title" \
        -H "Priority: $priority" \
        -H "Tags: robot_face" \
        --data-binary "$body" \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
}

# Send approval request with action buttons and confidence levels
ntfy_approval() {
    local phase_name="$1" completion_conf="$2" readiness_conf="$3" next_phase="$4" details="$5"
    local body="Completion: ${completion_conf}
Next-phase readiness: ${readiness_conf}

${details}

Next: ${next_phase}
Tap a button to respond:"

    curl -fsS -X POST \
        -H "Title: ${phase_name} Complete" \
        -H "Priority: default" \
        -H "Tags: robot_face,white_check_mark" \
        -H "Actions: view, ✅ Continue, https://ntfy.sh/$NTFY_TOPIC/publish?message=CONTINUE, clear=true; view, 🛑 Stop, https://ntfy.sh/$NTFY_TOPIC/publish?message=STOP, clear=true" \
        --data-binary "$body" \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
}

# Wait for user to tap Continue or Stop
# Returns 0 for CONTINUE, 1 for STOP, 2 for timeout
wait_for_approval() {
    local timeout_s="$1"
    local start_time
    start_time=$(date +%s)
    local poll_since="$start_time"

    echo "Waiting for approval (timeout: ${timeout_s}s)..." | tee -a "$LOG"

    while true; do
        local now
        now=$(date +%s)
        local elapsed=$(( now - start_time ))

        if [[ $elapsed -ge $timeout_s ]]; then
            echo "Approval timeout after ${timeout_s}s" | tee -a "$LOG"
            return 2
        fi

        # Poll for response messages since we sent the approval request
        local response
        response=$(curl -fsS "https://ntfy.sh/$NTFY_TOPIC/json?poll=1&since=${poll_since}" 2>/dev/null || echo "")

        if echo "$response" | grep -q '"message":"CONTINUE"'; then
            echo "User approved: CONTINUE" | tee -a "$LOG"
            return 0
        fi

        if echo "$response" | grep -q '"message":"STOP"'; then
            echo "User chose: STOP" | tee -a "$LOG"
            return 1
        fi

        sleep 30
    done
}

# Wait until we're in awake hours before sending notifications
wait_for_awake_hours() {
    local hour
    hour=$(date +%H)
    hour=$((10#$hour))  # force base-10

    if [[ $hour -ge $SLEEP_START || $hour -lt $SLEEP_END ]]; then
        echo "Sleep hours (${SLEEP_START}:00-${SLEEP_END}:00). Waiting..." | tee -a "$LOG"
        while true; do
            hour=$(date +%H)
            hour=$((10#$hour))
            if [[ $hour -ge $SLEEP_END && $hour -lt $SLEEP_START ]]; then
                echo "Awake hours — proceeding with notification." | tee -a "$LOG"
                break
            fi
            sleep 300  # check every 5 min
        done
    fi
}

# Assess confidence based on test results and git state
# Writes results to a temp file to avoid stdout pollution from npm/pytest
assess_confidence() {
    local pytest_result=0 vitest_result=0 build_result=0
    local completion="HIGH" readiness="HIGH"
    local details=""
    local _conf_tmp
    _conf_tmp="$(mktemp)"

    # Check Python tests (redirect all output to /dev/null)
    cd "$REPO_DIR"
    if python3 -m pytest tests/ -q --tb=no >/dev/null 2>&1; then
        local test_count
        test_count=$(python3 -m pytest tests/ -q --tb=no 2>/dev/null | tail -1)
        details="Python tests: ${test_count:-pass}"
    else
        pytest_result=1
        completion="MEDIUM"
        details="Python tests: SOME FAILURES"
    fi

    # Check if frontend build works (if node available)
    if command -v node &>/dev/null && [[ -f "$REPO_DIR/web/frontend/package.json" ]]; then
        if [[ -d "$REPO_DIR/web/frontend/node_modules" ]]; then
            cd "$REPO_DIR/web/frontend"
            if npm run build >/dev/null 2>&1; then
                details="$details\nReact build: clean"
            else
                build_result=1
                completion="MEDIUM"
                details="$details\nReact build: FAILED"
            fi

            if npm test >/dev/null 2>&1; then
                local vtest_count
                vtest_count=$(npm test 2>&1 | grep -oP '\d+ passed' | head -1)
                details="$details\nVitest: ${vtest_count:-pass}"
            else
                vitest_result=1
                completion="MEDIUM"
                details="$details\nVitest: SOME FAILURES"
            fi
        else
            details="$details\nReact: node_modules not installed (npm install needed)"
            readiness="MEDIUM"
        fi
    fi

    # Check for uncommitted changes
    cd "$REPO_DIR"
    if ! git diff --quiet 2>/dev/null; then
        completion="MEDIUM"
        details="$details\nWARNING: uncommitted changes in working tree"
    fi

    # If anything failed, readiness drops
    if [[ $pytest_result -ne 0 || $build_result -ne 0 ]]; then
        readiness="LOW"
    fi

    # Write to temp file to avoid stdout pollution
    {
        echo "$completion"
        echo "$readiness"
        echo -e "$details"
    } > "$_conf_tmp"
    cat "$_conf_tmp"
    rm -f "$_conf_tmp"
}

# --- Failure trap ---
NTFY_SENT=0
_failure_ntfy() {
    local rc=$?
    [[ $NTFY_SENT -eq 1 ]] && return
    [[ $rc -eq 0 ]] && return
    local body="chatwire-loop wrapper exited rc=$rc"
    if [[ -n "${LOG:-}" && -f "${LOG:-}" ]]; then
        body="$(tail -30 "$LOG" 2>/dev/null)"
    fi
    ntfy_send "chatwire-loop FAILED (exit $rc)" "high" "$body"
}
trap _failure_ntfy EXIT

# --- Sanity ---
[[ -f "$HANDOFF" ]] || { echo "HANDOFF.md not found at $HANDOFF" >&2; exit 2; }

# --- Extract §6 prompt from HANDOFF.md ---
# §6 is a fenced code block after "## 6." heading. Extract content between ``` fences.
extract_section6() {
    sed -n '/^## 6\./,$ p' "$HANDOFF" \
        | sed -n '/^```$/,/^```$/ { /^```$/d; p; }'
}

# --- Extract phase name from HANDOFF.md §1 or title ---
extract_phase_name() {
    head -1 "$HANDOFF" | sed 's/^# Handoff — //' | sed 's/ *$//'
}

# --- Extract next phase from HANDOFF.md §5 ---
extract_next_phase() {
    sed -n '/^## 5\./,/^## 6\./ p' "$HANDOFF" | grep -m1 '^\- ' | sed 's/^- //' || echo "See HANDOFF.md §5"
}

# --- Permission scoping ---
ALLOWED_TOOLS="Read,Edit,Write,Glob,Grep,Agent,WebFetch,WebSearch,Bash(git *),Bash(gh *),Bash(ssh *),Bash(scp *),Bash(rsync *),Bash(python*),Bash(pip*),Bash(pytest*),Bash(npm*),Bash(npx*),Bash(node*),Bash(curl *),Bash(cat *),Bash(head *),Bash(tail *),Bash(ls *),Bash(mkdir *),Bash(cp *),Bash(diff *),Bash(wc *),Bash(which *),Bash(sleep *),Bash(date *),Bash(md5sum *),Bash(sha256sum *)"

DISALLOWED_TOOLS="Bash(rm -rf /*),Bash(sudo*),Bash(kubectl*),Bash(helm*),Bash(docker*),Bash(ansible*)"

# --- Preamble injected before §6 prompt ---
PREAMBLE='You are running in HEADLESS CHAINED MODE on plinux (mediafront). No human is present — Allen is reachable via ntfy topic '"$NTFY_TOPIC"' for urgent questions only.

Working directory: '"$REPO_DIR"'

Protocol:
1. Read docs/HANDOFF.md in full. It is your state file.
2. Pick ONE concrete unit of work from §3 or §4. Small wins preferred — a theme port, a config flag, a cleanup — anything that ships in one session.
3. Do the work: edit, test (if possible), commit, push to origin main.
4. If the work includes a version bump + ship cycle: bump _version.py, commit, tag vX.Y.Z, push tag (triggers PyPI via GH Actions), wait ~2min for PyPI CDN, then ssh mbair to upgrade + restart launchd agents, bump brew tap formula.
5. When done: rewrite HANDOFF.md to reflect the new state. Update §1 (state), §2 (what shipped), §3 (follow-ups), and §6 (verbatim prompt for the NEXT session). Commit and push the updated HANDOFF.md.
6. If you hit a blocker you cannot resolve, send a message to ntfy: curl -d "BLOCKED: <reason>" https://ntfy.sh/'"$NTFY_TOPIC"'

Deployment (mbair):
- SSH to mbair works from this host. Example: ssh mbair "hostname"
- mbair PATH is bare over SSH. Use full paths:
    brew:      /usr/local/bin/brew
    pip:       ~/.local/pipx/venvs/chatwire/bin/python -m pip
    launchctl: /bin/launchctl
    curl:      /usr/bin/curl
- Upgrade chatwire:  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple/ chatwire==X.Y.Z"
- Inject a plugin:   ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir chatwire-telegram"
- Restart services:  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.bridge && /bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.keepawake"
- Health check:      ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"
- Brew tap update: clone/pull github.com/allenbina/homebrew-tap on plinux, edit the formula, commit, push.
- Visual QA (screenshots) requires mbair GUI tools not available headless — skip and note in HANDOFF.md.

Node.js / npm:
- Node 22 is available via nvm. If `node` is not found, run:
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
- React frontend is at web/frontend/. Run `npm install` if node_modules is missing.
- Run `npm run build` to produce dist/ and `npm test` for Vitest.

Hard rules:
- Never force-push. Never push to branches other than main.
- Never delete user files or directories outside the repo.
- Commit early, commit often. Each commit should be atomic and well-described.
- Do not attempt interactive commands (no vim, no less, no read from stdin).

Here is the opening prompt from the previous session:'

# === Main loop ===
STAMP="$(date +%Y-%m-%d-%H%M%S)"
LOG="$LOGS_DIR/$STAMP.log"

{
    echo "=== chatwire-loop fire ==="
    echo "Host:       $(hostname)"
    echo "Model:      $MODEL (fallback $FALLBACK_MODEL)"
    if [[ -n "$BUDGET_USD" ]]; then echo "Budget:     \$$BUDGET_USD/session"
    else                            echo "Budget:     none (subscription rate-limit)"
    fi
    echo "Max iter:   $MAX_ITERATIONS per phase"
    echo "Max phases: $MAX_PHASES"
    echo "Timeout:    ${SESSION_TIMEOUT_M}m/session (0=none)"
    echo "Auth:       subscription (ANTHROPIC_API_KEY unset)"
    if [[ -n "${_ANTHROPIC_API_KEY_WAS_SET:-}" ]]; then
        echo "            NOTE: ANTHROPIC_API_KEY was set in env; unset for this run"
    fi
    echo "Started:    $(date -Iseconds)"
    echo
} | tee "$LOG"

phase=0
while [[ $phase -lt $MAX_PHASES ]]; do
    phase=$((phase + 1))
    echo "========== PHASE $phase ==========" | tee -a "$LOG"

    iteration=0
    while [[ $iteration -lt $MAX_ITERATIONS ]]; do
        iteration=$((iteration + 1))
        echo "--- Session $iteration / $MAX_ITERATIONS (Phase $phase) ---" | tee -a "$LOG"

        # Extract current §6
        prompt_body="$(extract_section6)"
        if [[ -z "$prompt_body" ]]; then
            echo "§6 is empty — nothing to seed. Stopping." | tee -a "$LOG"
            ntfy_send "chatwire-loop stopped (§6 empty)" "default" "HANDOFF.md §6 was empty. Loop halted."
            NTFY_SENT=1
            break 2
        fi

        # Record §6 hash to detect changes after session
        section6_hash_before="$(echo "$prompt_body" | md5sum | cut -d' ' -f1)"

        # Compose full prompt
        full_prompt="$PREAMBLE

$prompt_body"

        if [[ $DRY_RUN -eq 1 ]]; then
            echo "=== DRY RUN — would send this prompt ===" | tee -a "$LOG"
            echo "$full_prompt" | tee -a "$LOG"
            echo "=== END DRY RUN ===" | tee -a "$LOG"
            exit 0
        fi

        echo "Firing claude -p ($(date -Iseconds))..." | tee -a "$LOG"

        # Fire
        session_exit=0
        budget_args=()
        if [[ -n "$BUDGET_USD" ]]; then
            budget_args=(--max-budget-usd "$BUDGET_USD")
        fi

        timeout_args=()
        if [[ $SESSION_TIMEOUT_M -gt 0 ]]; then
            timeout_args=(timeout "${SESSION_TIMEOUT_M}m")
        fi

        "${timeout_args[@]}" claude -p "$full_prompt" \
            --model "$MODEL" \
            --fallback-model "$FALLBACK_MODEL" \
            "${budget_args[@]}" \
            --permission-mode acceptEdits \
            --output-format text \
            --allowedTools "$ALLOWED_TOOLS" \
            --disallowedTools "$DISALLOWED_TOOLS" \
            >> "$LOG" 2>&1 || session_exit=$?

        echo "Session $iteration ended (exit=$session_exit, $(date -Iseconds))" | tee -a "$LOG"

        # --- Timeout recovery (exit 124 = killed by timeout) ---
        if [[ $session_exit -eq 124 ]]; then
            echo "Session $iteration TIMED OUT after ${SESSION_TIMEOUT_M}m — spawning doctor" | tee -a "$LOG"
            ntfy_send "chatwire-loop session $iteration timed out — diagnosing" "high" "Session hung for ${SESSION_TIMEOUT_M}m. Doctor session spawning."

            doctor_prompt="DOCTOR MODE: The previous chatwire-loop session timed out after ${SESSION_TIMEOUT_M} minutes.

Working directory: $REPO_DIR

Your job:
1. Run 'git status' and 'git diff' to check for partial uncommitted work.
2. Read docs/HANDOFF.md to understand what chunk was being worked on.
3. Read the last 50 lines of the session log at $LOG.
4. If there is partial work that can be committed, commit it. Then rewrite HANDOFF.md §6 with a prompt to RETRY or CONTINUE the failed chunk (inside a fenced code block).
5. If the work is unrecoverable or you cannot diagnose the issue, write 'NEEDS_INTERVENTION' in §6 (inside a fenced code block) and stop.
6. Be concise. Do not start implementing — just diagnose and set up the next attempt."

            doctor_exit=0
            timeout 5m claude -p "$doctor_prompt" \
                --model "$MODEL" \
                --fallback-model "$FALLBACK_MODEL" \
                --permission-mode acceptEdits \
                --output-format text \
                --allowedTools "$ALLOWED_TOOLS" \
                --disallowedTools "$DISALLOWED_TOOLS" \
                >> "$LOG" 2>&1 || doctor_exit=$?

            echo "Doctor session ended (exit=$doctor_exit)" | tee -a "$LOG"

            if [[ $doctor_exit -ne 0 ]]; then
                echo "Doctor session also failed. Stopping." | tee -a "$LOG"
                ntfy_send "chatwire-loop NEEDS INTERVENTION" "max" "Both session $iteration and doctor failed. Manual fix required."
                NTFY_SENT=1
                break 2
            fi

            new_s6="$(extract_section6)"
            if echo "$new_s6" | grep -qi 'NEEDS_INTERVENTION'; then
                echo "Doctor says: needs intervention. Stopping." | tee -a "$LOG"
                ntfy_send "chatwire-loop NEEDS INTERVENTION" "max" "Doctor diagnosed but cannot self-heal."
                NTFY_SENT=1
                break 2
            fi

            echo "Doctor recovered — continuing loop with updated §6" | tee -a "$LOG"
            ntfy_send "chatwire-loop doctor recovered" "default" "Self-healed after timeout. Continuing."
            section6_hash_before="invalid-force-chain"
            continue
        fi

        # --- Non-timeout failure ---
        if [[ $session_exit -ne 0 ]]; then
            echo "Non-zero exit ($session_exit). Spawning doctor." | tee -a "$LOG"
            ntfy_send "chatwire-loop session $iteration FAILED (exit $session_exit)" "high" "$(tail -10 "$LOG")"

            doctor_prompt="DOCTOR MODE: The previous chatwire-loop session exited with code $session_exit (non-zero).

Working directory: $REPO_DIR

Your job:
1. Run 'git status' and 'git diff' to check for partial uncommitted work.
2. Read docs/HANDOFF.md to understand what chunk was being worked on.
3. Read the last 50 lines of the session log at $LOG.
4. If there is partial work that can be committed, commit it. Then rewrite HANDOFF.md §6 with a prompt to RETRY the failed chunk (inside a fenced code block).
5. If the work is unrecoverable, write 'NEEDS_INTERVENTION' in §6 (inside a fenced code block).
6. Be concise. Diagnose only — do not implement."

            doctor_exit=0
            timeout 5m claude -p "$doctor_prompt" \
                --model "$MODEL" \
                --fallback-model "$FALLBACK_MODEL" \
                --permission-mode acceptEdits \
                --output-format text \
                --allowedTools "$ALLOWED_TOOLS" \
                --disallowedTools "$DISALLOWED_TOOLS" \
                >> "$LOG" 2>&1 || doctor_exit=$?

            echo "Doctor session ended (exit=$doctor_exit)" | tee -a "$LOG"

            if [[ $doctor_exit -ne 0 ]]; then
                echo "Doctor session also failed. Stopping." | tee -a "$LOG"
                ntfy_send "chatwire-loop NEEDS INTERVENTION" "max" "Both session $iteration and doctor failed."
                NTFY_SENT=1
                break 2
            fi

            new_s6="$(extract_section6)"
            if echo "$new_s6" | grep -qi 'NEEDS_INTERVENTION'; then
                echo "Doctor says: needs intervention. Stopping." | tee -a "$LOG"
                ntfy_send "chatwire-loop NEEDS INTERVENTION" "max" "Doctor diagnosed but cannot self-heal."
                NTFY_SENT=1
                break 2
            fi

            echo "Doctor recovered — continuing loop" | tee -a "$LOG"
            ntfy_send "chatwire-loop doctor recovered" "default" "Self-healed after error. Continuing."
            section6_hash_before="invalid-force-chain"
            continue
        fi

        # Safety net: commit any uncommitted HANDOFF.md changes the agent missed
        if git -C "$REPO_DIR" diff --quiet -- docs/HANDOFF.md 2>/dev/null; then
            : # clean
        else
            echo "HANDOFF.md has uncommitted changes — committing as safety net" | tee -a "$LOG"
            git -C "$REPO_DIR" add docs/HANDOFF.md
            git -C "$REPO_DIR" commit -m "chore: auto-commit HANDOFF.md after session $iteration"
        fi

        # --- Auto-deploy to mbair after each successful session ---
        if [[ -d "$REPO_DIR/web/frontend/dist" ]]; then
            echo "Auto-deploying to mbair..." | tee -a "$LOG"
            local site="/Users/allen/.local/pipx/venvs/chatwire/lib/python3.14/site-packages/web"
            ssh mbair "rm -rf $site/frontend/dist" 2>/dev/null || true
            scp -r "$REPO_DIR/web/frontend/dist" "mbair:$site/frontend/dist" 2>/dev/null || true
            ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web" 2>/dev/null || true
            local health
            health=$(ssh mbair "/usr/bin/curl -sf localhost:8723/healthz" 2>/dev/null || echo "FAILED")
            echo "mbair deploy: $health" | tee -a "$LOG"
        fi

        # Check if §6 changed
        new_prompt_body="$(extract_section6)"
        section6_hash_after="$(echo "$new_prompt_body" | md5sum | cut -d' ' -f1)"

        if [[ "$section6_hash_before" == "$section6_hash_after" ]]; then
            echo "§6 unchanged — iteration block complete." | tee -a "$LOG"
            break  # exit inner loop, go to approval
        fi

        echo "§6 updated — will chain to session $((iteration + 1))" | tee -a "$LOG"
        NTFY_SENT=0
    done

    # --- Phase approval checkpoint ---
    echo "=== Phase $phase approval checkpoint ===" | tee -a "$LOG"

    # Assess confidence
    phase_name="$(extract_phase_name)"
    next_phase="$(extract_next_phase)"

    # Run confidence assessment
    conf_output="$(assess_confidence 2>&1)"
    completion_conf="$(echo "$conf_output" | sed -n '1p')"
    readiness_conf="$(echo "$conf_output" | sed -n '2p')"
    conf_details="$(echo "$conf_output" | tail -n +3)"

    echo "Completion: $completion_conf" | tee -a "$LOG"
    echo "Readiness:  $readiness_conf" | tee -a "$LOG"
    echo "Details:    $conf_details" | tee -a "$LOG"

    # Wait for awake hours before notifying
    wait_for_awake_hours

    # Send approval request
    ntfy_approval "$phase_name" "$completion_conf" "$readiness_conf" "$next_phase" "$conf_details"
    NTFY_SENT=1

    # Wait for response
    approval_result=0
    wait_for_approval "$APPROVAL_TIMEOUT_S" || approval_result=$?

    case $approval_result in
        0)  # CONTINUE
            echo "User approved — continuing to next phase." | tee -a "$LOG"
            NTFY_SENT=0
            ;;
        1)  # STOP
            echo "User chose STOP. Exiting cleanly." | tee -a "$LOG"
            ntfy_send "chatwire-loop stopped by user" "default" "Loop stopped at phase $phase after user chose STOP."
            NTFY_SENT=1
            break
            ;;
        2)  # TIMEOUT
            echo "No response within timeout. Stopping safely." | tee -a "$LOG"
            ntfy_send "chatwire-loop paused (no response)" "default" "No approval received within timeout. Run the loop again to continue."
            NTFY_SENT=1
            break
            ;;
    esac
done

# Phase cap reached
if [[ $phase -ge $MAX_PHASES && $NTFY_SENT -eq 0 ]]; then
    echo "Phase cap ($MAX_PHASES) reached. Stopping." | tee -a "$LOG"
    ntfy_send "chatwire-loop stopped (phase cap $MAX_PHASES)" "default" "Reached max phases. Manual review recommended."
    NTFY_SENT=1
fi

echo "=== chatwire-loop finished at $(date -Iseconds) ===" | tee -a "$LOG"
