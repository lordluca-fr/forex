#!/bin/bash
# Fast-forward-only sync so the Mac Mini checkout never silently drifts from
# origin/master (same discipline as TigerTrading's daily_git_pull.sh, after
# the 2026-07-09 incident where a daemon host drifted 15 commits unnoticed).
# Never force-pulls, never restarts anything — deploying stays a manual step.
#
# Hercules-cron contract: silent when green, alert via @Herctradebot only on
# a real problem (diverged history, fetch/network failure), fail-loud exit.
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
LOG_FILE="${FOREX_GIT_PULL_LOG:-$REPO_DIR/logs/git_pull.log}"
mkdir -p "$(dirname "$LOG_FILE")"

ALERT() {
    "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (Mac Mini): $1" >>"$LOG_FILE" 2>&1
}

GIT_BIN="${FOREX_GIT_BIN:-}"
if [ -z "$GIT_BIN" ]; then
    for candidate in /opt/homebrew/bin/git /usr/bin/git /opt/bin/git; do
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
    ALERT "git fetch failed, check network/GitHub auth on the Mac Mini"
    exit 1
fi

if "$GIT_BIN" merge --ff-only origin/master >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK: $("$GIT_BIN" log -1 --format='%H %s')" >>"$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FF-ONLY FAILED - local repo has diverged, needs manual attention" >>"$LOG_FILE"
    ALERT "local checkout diverged from origin/master, fast-forward failed — needs manual attention"
    exit 1
fi
