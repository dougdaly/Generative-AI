#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RELOAD_FLAG="${RELOAD:-0}"
RELOAD_ARGS=""
if [[ "$RELOAD_FLAG" == "1" ]]; then
  RELOAD_ARGS="--reload"
fi

HOST="127.0.0.1"
ADD_PORT="${ADD_PORT:-8101}"
MULT_PORT="${MULT_PORT:-8102}"
EVAL_PORT="${EVAL_PORT:-8100}"

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Starting ADD  on http://${HOST}:${ADD_PORT}"
python -m uvicorn --app-dir notebooks/a2a_pemdas add_agent:app --host "$HOST" --port "$ADD_PORT" $RELOAD_ARGS &
pids+=($!)

echo "Starting MULT on http://${HOST}:${MULT_PORT}"
python -m uvicorn --app-dir notebooks/a2a_pemdas mult_agent:app --host "$HOST" --port "$MULT_PORT" $RELOAD_ARGS &
pids+=($!)

# Make the EVAL agent pick up the correct endpoints
export ADD_BASE_URL="http://${HOST}:${ADD_PORT}"
export MULT_BASE_URL="http://${HOST}:${MULT_PORT}"

echo "Starting EVAL on http://${HOST}:${EVAL_PORT}"
python -m uvicorn --app-dir notebooks/a2a_pemdas evaluate_agent:app --host "$HOST" --port "$EVAL_PORT" $RELOAD_ARGS &
pids+=($!)

echo ""
echo "PEMDAS agents running. Ctrl+C to stop."
echo "  ADD card : http://${HOST}:${ADD_PORT}/.well-known/agent.json"
echo "  MULT card: http://${HOST}:${MULT_PORT}/.well-known/agent.json"
echo "  EVAL card : http://${HOST}:${EVAL_PORT}/.well-known/agent.json"
echo "  ADD RPC  : http://${HOST}:${ADD_PORT}/a2a"
echo "  MULT RPC : http://${HOST}:${MULT_PORT}/a2a"
echo "  EVAL RPC  : http://${HOST}:${EVAL_PORT}/a2a"
echo ""

wait
