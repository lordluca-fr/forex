#!/bin/bash
# Install/refresh the Forex NAS sync stack from the repo checkout.
# Idempotent: safe to re-run after any git pull that touches
# deploy/systemd/ or the sync scripts.
#
#   /volume1/Forex/deploy/install_nas.sh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
UNIT_SRC="$SCRIPT_DIR/systemd"
UNITS="forex-gitpull.service forex-gitpull.timer forex-results-sync.service forex-results-sync.timer"

echo "Installing systemd units from $UNIT_SRC ..."
for unit in $UNITS; do
    sudo -n cp "$UNIT_SRC/$unit" "/etc/systemd/system/$unit"
    echo "  installed $unit"
done

sudo -n systemctl daemon-reload
for timer in forex-gitpull.timer forex-results-sync.timer; do
    sudo -n systemctl enable "$timer" >/dev/null 2>&1 || true
    sudo -n systemctl restart "$timer"
    echo "  enabled+started $timer"
done

mkdir -p "$REPO_DIR/logs" "$REPO_DIR/backtest/results"

echo
echo "Timers now scheduled:"
systemctl list-timers --all --no-pager | grep -i forex || true
