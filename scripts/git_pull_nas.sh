#!/bin/bash
# NAS counterpart to git_pull_mm.sh — same fast-forward-only discipline,
# same hercules-cron alert contract (silent when green, @Herctradebot on a
# real problem). Kept as a separate script (not shared) because the NAS
# needs its git binary discovery order flipped: DSM's own /usr/bin/git,
# where present, is often too old, so the Entware /opt/bin/git install is
# preferred here (see TigerTrading's daily_git_pull.sh comment history).
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
LOG_FILE="${FOREX_GIT_PULL_LOG:-$REPO_DIR/logs/git_pull.log}"
mkdir -p "$(dirname "$LOG_FILE")"

ALERT() { "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (NAS): $1" >>"$LOG_FILE" 2>&1; }

GIT_BIN="${FOREX_GIT_BIN:-}"
if [ -z "$GIT_BIN" ]; then
    for candidate in /opt/bin/git /usr/local/bin/git /usr/bin/git; do
        if [ -x "$candidate" ]; then GIT_BIN="$candidate"; break; fi
    done
fi
if [ -z "$GIT_BIN" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: no git binary found" >>"$LOG_FILE"
    ALERT "no git binary found on host, cannot sync"
    exit 1
fi

cd "$REPO_DIR" || exit 1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] fetching ($REPO_DIR)..." >>"$LOG_FILE"
if ! "$GIT_BIN" fetch origin master >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FETCH FAILED" >>"$LOG_FILE"
    ALERT "git fetch failed, check network/GitHub auth on the NAS"
    exit 1
fi

if "$GIT_BIN" merge --ff-only origin/master >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK: $("$GIT_BIN" log -1 --format='%H %s')" >>"$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FF-ONLY FAILED - local repo has diverged, needs manual attention" >>"$LOG_FILE"
    ALERT "local checkout diverged from origin/master, fast-forward failed — needs manual attention"
    exit 1
fi
