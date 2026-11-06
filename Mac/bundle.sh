#!/bin/bash
# Friday's server inside the Mac app, so it runs on any Apple-silicon Mac without Friday installed (HOSTED.md H108–H111,
# on the rhayrapetyan/download-site branch): a standalone Python (the python-build-standalone build uv installs) with
# Friday and its packages as uv.lock pins them, the website beside it, and the planner already compiled.
#
#   Mac/bundle.sh APP     fills APP/Contents/Resources/friday (build.sh calls it; web/dist must be built)
#
# The app is never written to while it runs: bytecode is compiled here, and the planner is compiled for any Apple
# silicon chip (NUMBA_CPU_NAME=generic, which the app sets too), so a downloaded copy finds it ready.
set -euo pipefail

APP="$1"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$APP/Contents/Resources/friday"
PYTHON_VERSION="3.12"
[ -f "$REPO/web/dist/index.html" ] || { echo "No web/dist: build the web app first" >&2; exit 1; }

echo "==> Bundling Python $PYTHON_VERSION"
uv python install --managed-python "$PYTHON_VERSION" >/dev/null 2>&1
# looked for outside any project: inside one, uv finds the project's .venv first (6 Nov: a venv was bundled, linked
# back to this Mac's Python and the repo)
FOUND="$(cd / && uv python find --managed-python --no-project "$PYTHON_VERSION")"
HOME_DIR="$(cd "$(dirname "$FOUND")/.." && pwd -P)"
if [ -f "$HOME_DIR/pyvenv.cfg" ] || [ ! -f "$HOME_DIR/lib/python$PYTHON_VERSION/os.py" ]; then
  echo "Not a standalone Python: $HOME_DIR" >&2
  exit 1
fi
[ -d "$RUNTIME" ] && rm -r "$RUNTIME"
mkdir -p "$RUNTIME"
ditto "$HOME_DIR" "$RUNTIME/python"
PY="$RUNTIME/python/bin/python$PYTHON_VERSION"

echo "==> Installing Friday and its packages into it"
WORK="$(mktemp -d)"
trap 'rm -r "$WORK"' EXIT
(cd "$REPO" && uv export --frozen --no-dev --no-emit-project --no-hashes --quiet -o "$WORK/packages.txt")
uv pip install --quiet --python "$PY" --break-system-packages -r "$WORK/packages.txt"
uv pip install --quiet --python "$PY" --break-system-packages --no-deps --reinstall-package friday "$REPO"
# what's installed must not point back at the repo, which lives in ~/Downloads (macOS asks about every read there)
if grep -rqs "$REPO" "$RUNTIME"/python/lib/python*/site-packages/*.pth; then
  echo "Friday was installed as a link to $REPO, not a copy" >&2
  exit 1
fi
echo "==> Leaving out what Friday never uses"
SITE="$(echo "$RUNTIME"/python/lib/python*/site-packages)"
# Google's descriptions of every API (108 MB): Friday reads only Calendar and Gmail (sync/google_auth.py)
find "$SITE/googleapiclient/discovery_cache/documents" -type f \
  ! -name "calendar.v3.json" ! -name "gmail.v1.json" ! -name "oauth2.v2.json" -delete
# the packages' own test suites, and the installers nobody runs inside the app
find "$SITE" -type d -name tests -prune -exec rm -r {} +
rm -r "$SITE"/pip "$SITE"/pip-*.dist-info
find "$RUNTIME/python/lib" -maxdepth 2 -type d \( -name idlelib -o -name turtledemo -o -name ensurepip \) -prune -exec rm -r {} +

mkdir -p "$RUNTIME/python/share/friday"
ditto "$REPO/web/dist" "$RUNTIME/python/share/friday/web"  # where the server looks beside its Python (web_dist)

echo "==> Compiling bytecode"
"$PY" -m compileall -q -j 0 "$RUNTIME/python/lib" >/dev/null || true  # a few test files of packages don't compile

echo "==> Compiling the planner (a sample week planned once)"
warm() {
  local port pid
  port="$("$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  NUMBA_CPU_NAME=generic FRIDAY_CONFIG="$WORK/friday.toml" "$PY" -m friday.server.main --data-dir "$WORK/demo" \
    demo --port "$port" --case maya >"$WORK/warm.txt" 2>&1 &
  pid=$!
  for _ in $(seq 1 480); do
    curl -s --max-time 2 "127.0.0.1:$port/api/q/status" | grep -q '"plan_id":[0-9]' && break
    kill -0 "$pid" 2>/dev/null || { tail -20 "$WORK/warm.txt" >&2; exit 1; }
    sleep 0.5
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
warm
ls "$RUNTIME"/python/lib/python*/site-packages/friday/engine/__pycache__/*.nbi >/dev/null 2>&1 \
  || { echo "The planner wasn't compiled into the app" >&2; exit 1; }
echo "    $(du -sh "$RUNTIME" | cut -f1) in $RUNTIME"
