#!/bin/bash
# The disk image people download (HOSTED.md H116): Friday.app beside an Applications folder to drag it onto, made on
# a Mac (hdiutil) from an app built on main (Mac/build.sh).
#
#   release/make-dmg.sh APP VERSION OUT_DIR     writes OUT_DIR/Friday-VERSION.dmg and prints its path
set -euo pipefail
APP="$1" VERSION="$2" OUT="$3"
[ -x "$APP/Contents/Resources/friday/python/bin/python3.12" ] || { echo "$APP has no server inside: build it on main" >&2; exit 1; }
STAGE="$(mktemp -d)"
trap 'rm -r "$STAGE"' EXIT
ditto "$APP" "$STAGE/Friday.app"  # keeps file times: the compiled planner inside is checked against them
ln -s /Applications "$STAGE/Applications"
mkdir -p "$OUT"
DMG="$OUT/Friday-$VERSION.dmg"
hdiutil create -quiet -volname "Friday $VERSION" -srcfolder "$STAGE" -format ULFO -ov "$DMG"
echo "$DMG"
