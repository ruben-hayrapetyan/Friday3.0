#!/bin/bash
# Friday as the Mac apps run it, installed outside this folder (29 Oct: "“Friday Test.app” would like to access files
# in your Downloads folder... they keep coming - this is most definitely a bug"). This repo lives in ~/Downloads, which
# macOS guards; a server run from it (an editable install) read its code and its pages there, and every solver worker
# it started asked again on the app's behalf. Installed as a copy, with the web app beside it, it reads nothing here.
#
#   scripts/deploy.sh               build the web app, install fridayd and its web app, restart Friday if it's open
#   scripts/deploy.sh --no-web      the Python only (the web app as last built)
#   scripts/deploy.sh --no-restart  install, and leave the running Friday as it is
#
# Friday and Friday Test both run ~/.local/bin/fridayd, so both pick up what this installs. After changing Python or
# the web app, this is how the change reaches them (a restart alone runs what was installed last).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PNPM="pnpm@10.12.1"
WEB=true RESTART=true
for arg in "$@"; do
  case "$arg" in
    --no-web) WEB=false ;;
    --no-restart) RESTART=false ;;
    *) echo "usage: $0 [--no-web] [--no-restart]" >&2; exit 2 ;;
  esac
done

if $WEB; then
  echo "==> Building the web app"
  (cd "$REPO/web" && npx --yes "$PNPM" build >/dev/null)
fi
[ -f "$REPO/web/dist/index.html" ] || { echo "No web/dist: build the web app first (drop --no-web)" >&2; exit 1; }

echo "==> Installing fridayd as a copy"
uv tool install --force --reinstall "$REPO" >/dev/null 2>&1
PREFIX="$(uv tool dir)/friday"
mkdir -p "$PREFIX/share/friday/web"
rsync -a --delete "$REPO/web/dist/" "$PREFIX/share/friday/web/"
# what's installed must not point back here
if grep -rqs "$REPO" "$PREFIX"/lib/python*/site-packages/*.pth; then
  echo "fridayd is still an editable install of $REPO" >&2
  exit 1
fi
echo "    $PREFIX"

if $RESTART && pgrep -f "fridayd serve$" >/dev/null; then
  echo "==> Restarting Friday"
  osascript -e 'quit app "Friday"' >/dev/null 2>&1 || true
  # until the old server has let go of its port: a new one started sooner can't bind it, and Friday won't open
  for _ in $(seq 1 120); do
    pgrep -f "fridayd serve$" >/dev/null || lsof -ti tcp:8765 -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 0.5
  done
  if lsof -ti tcp:8765 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "The old server is still holding port 8765; quit Friday and open it again." >&2
    exit 1
  fi
  open -a /Applications/Friday.app
  up=false
  for _ in $(seq 1 120); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8765/api/q/status)" = "200" ] && up=true && break
    sleep 0.5
  done
  if ! $up; then
    echo "Friday didn't answer within a minute; open it again." >&2
    exit 1
  fi
fi
echo "Done."
