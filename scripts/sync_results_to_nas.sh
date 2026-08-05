#!/bin/bash
# Sync Mac Mini backtest state (results/ + leaderboard.csv) to the NAS
# backup. Pull-based, runs on the NAS (forex-results-sync.timer, 5-min),
# same one-directional Mac Mini -> NAS pattern as TigerTrading's
# sync_state_from_mm.sh, minus its day-counter guard: this is research
# output, not real-money state, so a plain mirror is enough.
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
LOG_FILE="${FOREX_SYNC_LOG:-$REPO_DIR/logs/results_sync.log}"
mkdir -p "$(dirname "$LOG_FILE")"

: "${FOREX_MM_HOST:=djaka_mm@192.168.18.32}"
: "${FOREX_MM_REPO_DIR:=/Users/djaka_mm/projects/forex}"
: "${FOREX_NAS_ROOT:=$REPO_DIR}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no"

LOG() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG_FILE"; }
ALERT() { "$SCRIPT_DIR/hercron_send.sh" "FOREX SYNC (NAS): $1" >>"$LOG_FILE" 2>&1; }

if ! ssh $SSH_OPTS "$FOREX_MM_HOST" true 2>/dev/null; then
    LOG "Mac Mini unreachable over ssh — skipping (not alerting, transient network blips are expected)"
    exit 0
fi

mkdir -p "$FOREX_NAS_ROOT/backtest/results"

LOG "Syncing backtest results from Mac Mini..."
if ! rsync -az --delete -e "ssh $SSH_OPTS" \
    "${FOREX_MM_HOST}:${FOREX_MM_REPO_DIR}/backtest/results/" "$FOREX_NAS_ROOT/backtest/results/" >>"$LOG_FILE" 2>&1; then
    LOG "ERROR: results/ rsync failed"
    ALERT "backtest results rsync from Mac Mini failed — check logs/results_sync.log"
    exit 1
fi

LOG "Syncing leaderboard.csv from Mac Mini..."
if ! rsync -az -e "ssh $SSH_OPTS" \
    "${FOREX_MM_HOST}:${FOREX_MM_REPO_DIR}/backtest/leaderboard.csv" "$FOREX_NAS_ROOT/backtest/leaderboard.csv" >>"$LOG_FILE" 2>&1; then
    LOG "ERROR: leaderboard.csv rsync failed"
    ALERT "leaderboard.csv rsync from Mac Mini failed — check logs/results_sync.log"
    exit 1
fi

LOG "Sync complete."
