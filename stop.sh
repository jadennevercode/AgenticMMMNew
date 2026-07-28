#!/usr/bin/env bash
#
# stop.sh — stop the AI-Native MMM platform services started by ./start.sh.
#
# Usage:
#   ./stop.sh            # stop both services
#   ./stop.sh backend    # stop only the backend
#   ./stop.sh frontend   # stop only the frontend
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"

# stop_service <name> — graceful SIGTERM, then SIGKILL the whole process group.
stop_service() {
  local name="$1"
  local pidfile="$RUN_DIR/$name.pid"

  if [[ ! -f "$pidfile" ]]; then
    echo "• $name: no pidfile, nothing to stop"
    return
  fi

  local pid
  pid="$(cat "$pidfile")"

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    echo "• $name: not running (stale pidfile removed)"
    rm -f "$pidfile"
    return
  fi

  echo "→ stopping $name (pid $pid)"
  # Kill the process group so child workers (uvicorn reloader, vite esbuild) die too.
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true

  # Wait up to 5s for a clean exit, then force-kill.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "  $name did not exit — sending SIGKILL"
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi

  rm -f "$pidfile"
  echo "✓ $name stopped"
}

target="${1:-all}"
case "$target" in
  backend)  stop_service backend ;;
  frontend) stop_service frontend ;;
  all)      stop_service frontend; stop_service backend ;;
  *)
    echo "usage: $0 [backend|frontend|all]" >&2
    exit 2
    ;;
esac
