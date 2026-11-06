#!/bin/bash
# Your Friday as everyone gets it (HOSTED.md H115, on rhayrapetyan/download-site): the packaged Mac app, with Friday's
# server, its own Python, the website and the compiled planner inside (Mac/build.sh, Mac/bundle.sh), installed in
# /Applications and opened. Your data stays in ~/.local/share/friday. The app reads nothing in this repo, which lives
# in ~/Downloads, where macOS asks about every read (29 Oct: "“Friday Test.app” would like to access files in your
# Downloads folder... they keep coming").
#
#   scripts/deploy.sh               build the app and install it, restarting Friday
#   scripts/deploy.sh --no-restart  build the app into Mac/build only; Friday keeps running what it has
#
# The `friday` command (the CLI assistants use) is installed too, as a copy in ~/.local/bin.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
RESTART=true
for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART=false ;;
    *) echo "usage: $0 [--no-restart]" >&2; exit 2 ;;
  esac
done

echo "==> Installing the friday command as a copy"
uv tool install --force --reinstall "$REPO" >/dev/null 2>&1

if ! $RESTART; then
  "$REPO/Mac/build.sh"
  echo "Built Mac/build/Friday.app; Friday keeps running what it has."
  exit 0
fi
"$REPO/Mac/build.sh" --install
up=false
for _ in $(seq 1 240); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8765/api/q/status)" = "200" ] && up=true && break
  sleep 0.5
done
if ! $up; then
  echo "Friday didn't answer within two minutes; open it again." >&2
  exit 1
fi
echo "Done."
