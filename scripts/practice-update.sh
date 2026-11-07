#!/bin/bash
# A practice update in Friday Test, all on this Mac (HOSTED.md H148, on rhayrapetyan/download-site): Friday Test is
# built at this version, looking for updates at a feed served on this Mac, which offers the same Friday Test numbered
# one higher, with practice notes. Opening Friday Test shows the update popup; Update downloads it, restarts into it
# with the same test user, and shows what's new. Nothing goes to the site or the hub.
#
#   scripts/practice-update.sh          build, serve the practice feed on 127.0.0.1:8796, open Friday Test
#   scripts/practice-update.sh stop     stop serving the practice feed
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8796
FEED="http://127.0.0.1:$PORT/updates.json"
WORK="$REPO/Mac/build/practice-update"
TEST_APP="$REPO/Mac/build/Friday Test.app"

stop() { pkill -f "http.server $PORT --bind 127.0.0.1" 2>/dev/null || true; }
if [ "${1:-}" = stop ]; then stop; echo "The practice feed is stopped."; exit 0; fi

OLD="$(tr -d '[:space:]' < "$REPO/VERSION")"
IFS=. read -r MAJOR MINOR PATCH <<< "$OLD"
NEW="$MAJOR.$MINOR.$((PATCH + 1))"

echo "==> Friday Test $OLD, looking at the practice feed"
osascript -e 'tell application id "com.rubenhayrapetyan.friday.test" to quit' 2>/dev/null || true
FRIDAY_PRACTICE_FEED="$FEED" "$REPO/Mac/build.sh" --test

echo "==> The same Friday Test as $NEW, on a disk image"
[ -d "$WORK" ] && rm -r "$WORK"
mkdir -p "$WORK/stage" "$WORK/site/downloads"
ditto "$TEST_APP" "$WORK/stage/Friday.app"
plutil -replace CFBundleShortVersionString -string "$NEW" "$WORK/stage/Friday.app/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$NEW" "$WORK/stage/Friday.app/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$WORK/stage/Friday.app"
DMG="$WORK/site/downloads/Friday-$NEW.dmg"
hdiutil create -quiet -volname "Friday Test $NEW" -srcfolder "$WORK/stage" -format ULFO "$DMG"

python3 - "$DMG" "$NEW" "$OLD" "$FEED" > "$WORK/site/updates.json" <<'PY'
import hashlib, json, os, sys
dmg, new, old, feed = sys.argv[1:]
base = feed.rsplit("/", 1)[0]
digest = hashlib.sha256(open(dmg, "rb").read()).hexdigest()
notes = {"summary": f"Practice: Friday Test {new}, made on this Mac to try updating.",
         "new": ["Nothing new: this version only has a higher number."],
         "changed": [], "fixed": []}
print(json.dumps({"current": new, "versions": [
    {"version": new, "released": "2026-11-07", "url": f"{base}/downloads/Friday-{new}.dmg", "sha256": digest,
     "bytes": os.path.getsize(dmg), "minimum_macos": "14.0", "notes": notes}]}, indent=2))
PY

echo "==> Serving the practice feed at $FEED"
stop
nohup python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$WORK/site" > "$WORK/feed.txt" 2>&1 &
sleep 1
curl -sf "$FEED" > /dev/null || { echo "The practice feed didn't start" >&2; exit 1; }

open "$TEST_APP"
echo "Friday Test $OLD is open: skip or finish the walk, and the update popup offers $NEW."
echo "When you're done: scripts/practice-update.sh stop"
