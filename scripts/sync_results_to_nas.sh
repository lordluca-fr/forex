#!/bin/bash
# Sync Mac Mini backtest state (results/ + leaderboard.csv) to the NAS
# backup. Pull-based, runs on the NAS (forex-results-sync.timer, 5-min),
# same one-directional Mac Mini -> NAS pattern as TigerTrading's
# sync_state_from_mm.sh, minus its day-counter guard: this is research
# output, not real-money state, so a plain mirror is enough.
#
# Unreachable-host handling: TigerTrading's equivalent script skips
# unreachable-Mac-Mini quietly because a separate watchdog.service already
# owns down-detection/alerting there. Forex has no such watchdog, so a
# silent skip here would mean a genuinely dead Mac Mini (not just a
# transient blip) goes unnoticed forever. Instead this tracks how long the
# Mac Mini has been unreachable and alerts once it crosses
# FOREX_UNREACHABLE_THRESHOLD_SECS (default 600s, matching TigerTrading's
# TT_FAIL_THRESHOLD_SECS) — long enough to ride out a single missed 5-min
# check, short enough to still notice a real outage same-session.
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
LOG_FILE="${FOREX_SYNC_LOG:-$REPO_DIR/logs/results_sync.log}"
STATE_DIR="$REPO_DIR/.sync_state"
DOWN_SINCE_FILE="$STATE_DIR/mm_down_since"
DOWN_ALERTED_FILE="$STATE_DIR/mm_down_alerted"
RSYNC_ALERTED_FILE="$STATE_DIR/rsync_failed_alerted"
mkdir -p "$(dirname "$LOG_FILE")" "$STATE_DIR"

: "${FOREX_MM_HOST:=djaka_mm@192.168.18.32}"
: "${FOREX_MM_REPO_DIR:=/Users/djaka_mm/projects/forex}"
: "${FOREX_NAS_ROOT:=$REPO_DIR}"
: "${FOREX_UNREACHABLE_THRESHOLD_SECS:=600}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no"

LOG() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG_FILE"; }
ALERT() { "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (NAS): $1" >>"$LOG_FILE" 2>&1; }
ALERT_ONCE() {
    if [ ! -f "$RSYNC_ALERTED_FILE" ]; then
        ALERT "$1"
        touch "$RSYNC_ALERTED_FILE"
    else
        LOG "(already alerted for this rsync failure, not re-sending)"
    fi
}

if ! ssh $SSH_OPTS "$FOREX_MM_HOST" true 2>/dev/null; then
    NOW=$(date +%s)
    if [ ! -f "$DOWN_SINCE_FILE" ]; then
        echo "$NOW" >"$DOWN_SINCE_FILE"
        LOG "Mac Mini unreachable over ssh — down-timer started"
    else
        DOWN_SINCE=$(cat "$DOWN_SINCE_FILE")
        ELAPSED=$((NOW - DOWN_SINCE))
        if [ "$ELAPSED" -ge "$FOREX_UNREACHABLE_THRESHOLD_SECS" ] && [ ! -f "$DOWN_ALERTED_FILE" ]; then
            LOG "Mac Mini unreachable for ${ELAPSED}s (>= ${FOREX_UNREACHABLE_THRESHOLD_SECS}s threshold) — alerting"
            ALERT "Mac Mini unreachable over ssh for $((ELAPSED / 60))+ min — backtest results sync paused"
            touch "$DOWN_ALERTED_FILE"
        else
            LOG "Mac Mini unreachable over ssh — down for ${ELAPSED}s, below alert threshold"
        fi
    fi
    exit 0
fi

if [ -f "$DOWN_SINCE_FILE" ]; then
    if [ -f "$DOWN_ALERTED_FILE" ]; then
        ALERT "Mac Mini reachable again — resuming backtest results sync"
    fi
    rm -f "$DOWN_SINCE_FILE" "$DOWN_ALERTED_FILE"
fi

mkdir -p "$FOREX_NAS_ROOT/backtest/results"

LOG "Syncing backtest results from Mac Mini..."
if ! rsync -az --delete -e "ssh $SSH_OPTS" \
    "${FOREX_MM_HOST}:${FOREX_MM_REPO_DIR}/backtest/results/" "$FOREX_NAS_ROOT/backtest/results/" >>"$LOG_FILE" 2>&1; then
    LOG "ERROR: results/ rsync failed"
    ALERT_ONCE "backtest results rsync from Mac Mini failed — check logs/results_sync.log"
    exit 1
fi

# leaderboard.csv is deliberately NOT rsynced here even though it lives
# under backtest/ -- it's git-tracked (see backtest/README.md), and rsync
# writing to a git-tracked path leaves the working tree dirty relative to
# git's index without git ever knowing. That dirtiness then permanently
# blocks forex-gitpull.timer's `merge --ff-only` the next time Mac Mini
# pushes a leaderboard update (hit in practice 2026-08-06: NAS pull failed
# repeatedly with "local changes would be overwritten by merge" until this
# rsync was removed). leaderboard.csv reaches the NAS via the normal git
# pull path instead, same as every other tracked file.

if [ -f "$RSYNC_ALERTED_FILE" ]; then
    rm -f "$RSYNC_ALERTED_FILE"
    ALERT "recovered — backtest results sync succeeded again"
fi

LOG "Sync complete."
