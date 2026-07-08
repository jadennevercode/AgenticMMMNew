#!/usr/bin/env bash
#
# start.sh — boot the AI-Native MMM platform (backend + frontend).
#
#   Backend : FastAPI / uvicorn  -> http://127.0.0.1:8000
#   Frontend: Vite dev server    -> http://localhost:5173
#
# Usage:
#   ./start.sh            # start both services
#   ./start.sh backend    # start only the backend
#   ./start.sh frontend   # start only the frontend
#
# PIDs and logs live under .run/ (gitignored). Stop with ./stop.sh.
set -euo pipefail

# Enable job control so each backgrounded service gets its own process group,
# letting stop.sh kill the whole group (uvicorn reloader / vite workers) cleanly.
set -m

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
FRONTEND_PORT="5173"

# --- helpers ----------------------------------------------------------------

# is_running <pidfile> -> 0 if the recorded PID is alive
is_running() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 1
  local pid
  pid="$(cat "$pidfile")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_backend() {
  local pidfile="$RUN_DIR/backend.pid"
  local log="$RUN_DIR/backend.log"

  if is_running "$pidfile"; then
    echo "✓ backend already running (pid $(cat "$pidfile"))"
    return
  fi

  local py="$ROOT/backend/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    echo "✗ backend venv missing: $py" >&2
    echo "  create it with: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt" >&2
    return 1
  fi

  echo "→ starting backend on http://$BACKEND_HOST:$BACKEND_PORT (log: .run/backend.log)"
  (
    cd "$ROOT/backend"
    exec "$py" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) >"$log" 2>&1 &
  echo $! >"$pidfile"
  echo "✓ backend started (pid $(cat "$pidfile"))"
}

start_frontend() {
  local pidfile="$RUN_DIR/frontend.pid"
  local log="$RUN_DIR/frontend.log"

  if is_running "$pidfile"; then
    echo "✓ frontend already running (pid $(cat "$pidfile"))"
    return
  fi

  if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    echo "✗ frontend deps missing — run: (cd frontend && npm install)" >&2
    return 1
  fi

  echo "→ starting frontend on http://localhost:$FRONTEND_PORT (log: .run/frontend.log)"
  (
    cd "$ROOT/frontend"
    exec npm run dev -- --port "$FRONTEND_PORT"
  ) >"$log" 2>&1 &
  echo $! >"$pidfile"
  echo "✓ frontend started (pid $(cat "$pidfile"))"
}

# --- main -------------------------------------------------------------------

target="${1:-all}"
case "$target" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)      start_backend; start_frontend ;;
  *)
    echo "usage: $0 [backend|frontend|all]" >&2
    exit 2
    ;;
esac

echo
echo "Done. Tail logs with:  tail -f .run/backend.log .run/frontend.log"
echo "Stop everything with:  ./stop.sh"
