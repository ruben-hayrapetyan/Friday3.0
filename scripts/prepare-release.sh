#!/bin/bash
# Prepares a version of Friday for release (HOSTED.md H123, H134, H136, H174): sets the version (VERSION and the
# same number in both pyproject.toml, web/package.json and both uv.lock) and commits it, builds the Mac app with
# Friday's Google client, makes the disk image, and uploads it with its draft notes to the laptop. There it waits in
# the admin hub (https://laptop.tailnet.ts.net:8444/) for you to edit and approve the notes and press
# Release. Nothing is released here.
#
#   scripts/prepare-release.sh VERSION NOTES.json
#
# NOTES.json: {"summary": "one sentence", "new": [lines], "changed": [lines], "fixed": [lines]} (H143).
# FRIDAY_RELEASE_HOST is the laptop over ssh (default debian). FRIDAY_PREPARE_APP names an app already built, so its
# test needn't build one.
set -euo pipefail

VERSION="${1:-}" NOTES="${2:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${FRIDAY_RELEASE_HOST:-debian}"
die() { echo "Not prepared: $1" >&2; exit 1; }

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "the version should be a number like 0.2.0, not '$VERSION'"
[ -f "$NOTES" ] || die "no notes at '$NOTES'"
python3 - "$NOTES" <<'PY' || die "the notes need a summary sentence and at least one line under new, changed or fixed"
import json, sys
notes = json.load(open(sys.argv[1]))
assert isinstance(notes.get("summary"), str) and notes["summary"].strip()
assert all(isinstance(notes.get(k, []), list) for k in ("new", "changed", "fixed"))
assert any(line.strip() for k in ("new", "changed", "fixed") for line in notes.get(k, []))
PY
unset FRIDAY_GOOGLE_CLIENT  # downloads leave Google's client out (C77): Google lets in only listed test users
cd "$REPO"
git diff --quiet HEAD -- || die "commit or set aside your changes first: a version is built from a commit"

echo "==> Friday $VERSION"
# the number everywhere it's written (H174): VERSION, both pyproject.toml, web/package.json and both uv.lock
NUMBERED_SAID="$(python3 scripts/set_version.py "$VERSION")" || die "the version number couldn't be written into its files"
read -r -a NUMBERED <<< "$NUMBERED_SAID"
if ! git diff --quiet HEAD -- "${NUMBERED[@]}"; then
  git commit -q -m "Friday $VERSION, prepared for release" -- "${NUMBERED[@]}"
fi
COMMIT="$(git rev-parse HEAD)"

WORK="$(mktemp -d)"
trap 'rm -r "$WORK"' EXIT
APP="${FRIDAY_PREPARE_APP:-}"
if [ -z "$APP" ]; then
  Mac/build.sh  # it looks for updates on the site, as every build but Friday Test does (H169)
  APP="$REPO/Mac/build/Friday.app"
fi

echo "==> Making the disk image"
mkdir "$WORK/stage"
ditto "$APP" "$WORK/stage/Friday.app"  # keeps file times: the compiled planner inside is checked against them
ln -s /Applications "$WORK/stage/Applications"
DMG="$WORK/Friday-$VERSION.dmg"
hdiutil create -quiet -volname "Friday $VERSION" -srcfolder "$WORK/stage" -format ULFO -ov "$DMG"
SHA="$(shasum -a 256 "$DMG" | cut -d' ' -f1)"
BYTES="$(stat -f %z "$DMG")"

python3 - "$NOTES" "$VERSION" "$SHA" "$BYTES" "$COMMIT" > "$WORK/candidate.json" <<'PY'
import json, sys
from datetime import datetime
notes, version, sha, size, commit = sys.argv[1:]
print(json.dumps({"version": version, "prepared": datetime.now().isoformat(timespec="seconds"), "sha256": sha,
                  "bytes": int(size), "commit": commit, "notes": json.load(open(notes)), "approved": False}, indent=2))
PY

echo "==> Uploading to the laptop ($HOST)"
# candidate.json goes last: the hub shows a version only once all of it has arrived
ssh "$HOST" "mkdir -p friday-releases/candidates/$VERSION && rm -f friday-releases/candidates/$VERSION/candidate.json"
scp -q "$DMG" "$HOST:friday-releases/candidates/$VERSION/Friday-$VERSION.dmg"
scp -q "$WORK/candidate.json" "$HOST:friday-releases/candidates/$VERSION/candidate.json"
echo "Friday $VERSION waits in the hub: https://laptop.tailnet.ts.net:8444/"
