#!/bin/bash
# Fast-forward-only sync so the Mac Mini checkout never silently drifts from
# origin/master (same discipline as TigerTrading's daily_git_pull.sh, after
# the 2026-07-09 incident where a daemon host drifted 15 commits unnoticed).
# Never force-pulls, never restarts anything — deploying stays a manual step.
#
# Hercules-cron contract: silent when green, alert via @Herctradebot only on
# a real problem (diverged history, fetch/network failure), fail-loud exit.
#
# Alerts fire once per failure episode, not once per run: at this script's
# 5-min cadence (vs TigerTrading's original once-daily), alerting on every
# failed run would spam Telegram every 5 min for as long as an outage lasts.
# A marker file tracks "already alerted for the current failure"; a
# following success clears it and sends one recovery note.
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
LOG_FILE="${FOREX_GIT_PULL_LOG:-$REPO_DIR/logs/git_pull.log}"
STATE_DIR="$REPO_DIR/.sync_state"
ALERTED_MARKER="$STATE_DIR/git_pull_mm.alerted"
mkdir -p "$(dirname "$LOG_FILE")" "$STATE_DIR"

ALERT_ONCE() {
    if [ ! -f "$ALERTED_MARKER" ]; then
        "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (Mac Mini): $1" >>"$LOG_FILE" 2>&1
        touch "$ALERTED_MARKER"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] (already alerted for this failure, not re-sending)" >>"$LOG_FILE"
    fi
}

CLEAR_ALERT_STATE() {
    if [ -f "$ALERTED_MARKER" ]; then
        rm -f "$ALERTED_MARKER"
        "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (Mac Mini): recovered — $1" >>"$LOG_FILE" 2>&1
    fi
}

GIT_BIN="${FOREX_GIT_BIN:-}"
if [ -z "$GIT_BIN" ]; then
    for candidate in /opt/homebrew/bin/git /usr/bin/git /opt/bin/git; do
        if [ -x "$candidate" ]; then GIT_BIN="$candidate"; break; fi
    done
fi
if [ -z "$GIT_BIN" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: no git binary found" >>"$LOG_FILE"
    ALERT_ONCE "no git binary found on host, cannot sync"
    exit 1
fi

cd "$REPO_DIR" || exit 1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] fetching ($REPO_DIR)..." >>"$LOG_FILE"
if ! "$GIT_BIN" fetch origin master >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FETCH FAILED" >>"$LOG_FILE"
    ALERT_ONCE "git fetch failed, check network/GitHub auth on the Mac Mini"
    exit 1
fi

if "$GIT_BIN" merge --ff-only origin/master >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK: $("$GIT_BIN" log -1 --format='%H %s')" >>"$LOG_FILE"
    CLEAR_ALERT_STATE "git pull succeeded ($("$GIT_BIN" log -1 --format='%h %s'))"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FF-ONLY FAILED - local repo has diverged, needs manual attention" >>"$LOG_FILE"
    ALERT_ONCE "local checkout diverged from origin/master, fast-forward failed — needs manual attention"
    exit 1
fi
