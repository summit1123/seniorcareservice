#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8003}"
PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME:-forsure.summit1123.co.kr}"
TUNNEL_TOKEN_FILE="${TUNNEL_TOKEN_FILE:-$HOME/.cloudflared/summit1123.token}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/.logs}"
START_TUNNEL="${START_TUNNEL:-auto}"

mkdir -p "$LOG_DIR"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] missing command: $1"
    exit 1
  }
}

require_cmd lsof
require_cmd python3
require_cmd cloudflared
require_cmd pgrep
require_cmd grep

PIDS=()

cleanup() {
  if ((${#PIDS[@]} == 0)); then
    return
  fi
  echo
  echo "[INFO] stopping processes started by this script..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "[INFO] root=$ROOT_DIR"
echo "[INFO] local app=http://$APP_HOST:$APP_PORT"
echo "[INFO] public url=https://$PUBLIC_HOSTNAME"

if lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[INFO] app port $APP_PORT is already listening; reusing it."
else
  echo "[INFO] starting app server..."
  (
    cd "$ROOT_DIR"
    python3 -m src.webapp.customer_decision_app --host "$APP_HOST" --port "$APP_PORT"
  ) > "$LOG_DIR/public-demo-app.log" 2>&1 &
  app_pid="$!"
  PIDS+=("$app_pid")
  echo "[INFO] app pid=$app_pid log=$LOG_DIR/public-demo-app.log"
fi

if [[ ! -f "$TUNNEL_TOKEN_FILE" ]]; then
  echo "[ERROR] tunnel token file not found: $TUNNEL_TOKEN_FILE"
  exit 1
fi

cloudflared_processes="$(pgrep -lf cloudflared 2>/dev/null || true)"
if printf '%s\n' "$cloudflared_processes" | grep -F "$TUNNEL_TOKEN_FILE" >/dev/null 2>&1; then
  echo "[INFO] summit1123 cloudflared connector is already running; reusing it."
elif [[ "$START_TUNNEL" == "true" ]]; then
  echo "[INFO] starting cloudflared connector..."
  cloudflared tunnel run --token-file "$TUNNEL_TOKEN_FILE" > "$LOG_DIR/public-demo-cloudflared.log" 2>&1 &
  cloudflared_pid="$!"
  PIDS+=("$cloudflared_pid")
  echo "[INFO] cloudflared pid=$cloudflared_pid log=$LOG_DIR/public-demo-cloudflared.log"
else
  echo "[WARN] this shell could not confirm a summit1123 cloudflared connector."
  echo "[WARN] if the public URL fails, use START_TUNNEL=true scripts/run_public_demo.sh to force-start it."
fi

echo
echo "[READY] https://$PUBLIC_HOSTNAME"
echo "[CHECK] curl -sS -I https://$PUBLIC_HOSTNAME/"

if ((${#PIDS[@]} > 0)); then
  echo "[INFO] keep this terminal open while sharing the public demo."
  wait
else
  echo "[INFO] no new process was started by this script."
fi
