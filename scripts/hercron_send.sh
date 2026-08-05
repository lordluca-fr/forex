#!/bin/bash
# hercron_send.sh — Send a message via @Herctradebot Telegram API
# Reads HERCRON_BOT_TOKEN and HERCRON_CHAT_ID from environment or .env file.
# Usage: hercron_send.sh <message> | echo "text" | hercron_send.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

BOT_TOKEN="${HERCRON_BOT_TOKEN:-}"
CHAT_ID="${HERCRON_CHAT_ID:-}"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "Error: HERCRON_BOT_TOKEN and HERCRON_CHAT_ID must be set (env or .env)" >&2
    exit 1
fi

API="https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"

if [ -n "${1:-}" ]; then
    TEXT="$*"
elif [ ! -t 0 ]; then
    TEXT=$(cat)
else
    echo "Usage: hercron_send.sh <message> or pipe to stdin" >&2
    exit 1
fi

PY=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$TEXT")

# Try Markdown first; on a parse rejection (e.g. unbalanced _ from names like
# regime_alert — Telegram 400 "can't parse entities") retry as plain text so
# the message is delivered rather than silently dropped. Exit nonzero only
# when BOTH attempts fail, so callers can detect real delivery failures.
RESP=$(curl -s -X POST "$API" -H "Content-Type: application/json" \
    -d "{\"chat_id\":$CHAT_ID,\"text\":$PY,\"parse_mode\":\"Markdown\"}")
if [[ "$RESP" == *'"ok":true'* ]]; then
    echo "OK"
    exit 0
fi
RESP=$(curl -s -X POST "$API" -H "Content-Type: application/json" \
    -d "{\"chat_id\":$CHAT_ID,\"text\":$PY}")
if [[ "$RESP" == *'"ok":true'* ]]; then
    echo "OK"
    exit 0
fi
echo "FAIL: ${RESP:0:200}" >&2
echo "FAIL"
exit 1
