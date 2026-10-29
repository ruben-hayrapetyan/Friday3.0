#!/bin/bash
# A brand-new user's Friday, beside yours and apart from it (28 Oct: "work on the startup sequence but I don't want to
# do this on my personal friday... assuming a completely new user").
#
# Each run starts a Friday of its own: a new data folder and config folder under ~/.local/share/friday-fresh, so no
# setup answers, no plan, no Google, no plugins, no Anthropic key; its own server port; and the web app served live
# from web/src on a port of its own, so the browser remembers nothing for it either (each port is a new origin). The
# server is set up the way the Mac app sets up a new user's (`fridayd init`: the detected time zone, bedtime 23:30,
# wake 07:30). Your Friday, its data in ~/.local/share/friday and its server on 8765, isn't touched.
#
#   scripts/fresh_user.sh               start a new user, and print where to open it
#   scripts/fresh_user.sh --no-claude   as a user without the `claude` command
#   scripts/fresh_user.sh --no-init     before the Mac app's set-up (no time zone or sleep yet)
#   scripts/fresh_user.sh --built       the built app (web/dist) from the server itself, instead of live from source
#   scripts/fresh_user.sh stop          stop the latest one (its folder stays, for a look afterwards)
#   scripts/fresh_user.sh list          the users made so far
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${FRIDAY_FRESH_ROOT:-$HOME/.local/share/friday-fresh}"
PNPM="pnpm@10.12.1"

free_port() {  # the first free port from $1
  python3 - "$1" <<'EOF'
import socket, sys
port = int(sys.argv[1])
while True:
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            print(port)
            break
    port += 1
EOF
}

wait_for() {  # until $1 answers, at most $2 seconds
  for _ in $(seq 1 $(($2 * 4))); do
    curl -s -o /dev/null --max-time 1 "$1" && return 0
    sleep 0.25
  done
  return 1
}

stop() {
  local dir
  dir="$(readlink "$ROOT/current" 2>/dev/null || true)"
  [ -n "$dir" ] && [ -f "$dir/ports" ] || { echo "No fresh user running."; return 0; }
  for port in $(cat "$dir/ports"); do
    for pid in $(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null); do kill "$pid" 2>/dev/null || true; done
  done
  rm "$ROOT/current"
  echo "Stopped. Its data stays in $dir"
}

case "${1:-}" in
  stop) stop; exit 0 ;;
  list) ls -1 "$ROOT" 2>/dev/null | grep -v '^current$' || echo "None yet."; exit 0 ;;
esac

NO_CLAUDE=false NO_INIT=false BUILT=false
for arg in "$@"; do
  case "$arg" in
    --no-claude) NO_CLAUDE=true ;;
    --no-init) NO_INIT=true ;;
    --built) BUILT=true ;;
    *) echo "usage: $0 [--no-claude] [--no-init] [--built] | stop | list" >&2; exit 2 ;;
  esac
done

[ -L "$ROOT/current" ] && stop >/dev/null  # one fresh user at a time

DIR="$ROOT/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$DIR/data" "$DIR/config"
SERVER_PORT="$(free_port 8790)"
WEB_PORT="$(free_port 5190)"

# Everything that could reach your Friday's files points into the new folders instead.
export FRIDAY_DATA_DIR="$DIR/data"
export FRIDAY_CONFIG="$DIR/config/friday.toml"
export FRIDAY_CALENDARS_READ_ONLY=1  # signed in to your real Google, it still never changes a calendar
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY XAI_API_KEY META_API_KEY FRIDAY_AI_KEY
$NO_CLAUDE && export FRIDAY_CLAUDE=none

cd "$REPO"
$NO_INIT || uv run fridayd --data-dir "$DIR/data" init </dev/null >"$DIR/init.out" 2>&1
# Both run on after this script ends, holding nothing of its terminal (or of a pipe it prints into).
nohup uv run fridayd --data-dir "$DIR/data" serve --port "$SERVER_PORT" </dev/null >"$DIR/server.out" 2>&1 &
echo "$SERVER_PORT" >"$DIR/ports"
if ! $BUILT; then
  (cd web && FRIDAY_SERVER="http://127.0.0.1:$SERVER_PORT" exec nohup npx --yes "$PNPM" exec vite --port "$WEB_PORT" \
    --strictPort </dev/null >"$DIR/web.out" 2>&1) &
  echo "$WEB_PORT" >>"$DIR/ports"
fi
ln -sfn "$DIR" "$ROOT/current"

wait_for "http://127.0.0.1:$SERVER_PORT/api/q/status" 120 || { echo "The server didn't start; see $DIR/server.out" >&2; exit 1; }
URL="http://127.0.0.1:$SERVER_PORT/"
if ! $BUILT; then
  wait_for "http://localhost:$WEB_PORT/" 60 || { echo "The web app didn't start; see $DIR/web.out" >&2; exit 1; }
  URL="http://localhost:$WEB_PORT/"
fi

echo "A new user's Friday is running."
echo "  Open:    $URL"
echo "  Server:  127.0.0.1:$SERVER_PORT$($NO_CLAUDE && echo ', without Claude')$($NO_INIT && echo ', not set up yet')"
echo "  Data:    $DIR"
echo "  Stop:    scripts/fresh_user.sh stop"
