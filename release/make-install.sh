#!/bin/bash
# The site's install script for a version (HOSTED.md H131): release/install-template.sh with the version, the disk
# image's checksum and the site's address filled in, written to site/install.sh.
#
#   release/make-install.sh VERSION [SITE]     SITE defaults to the tailnet address (H103) until there's a domain
set -euo pipefail
VERSION="$1"
SITE="${2:-https://laptop.tailnet.ts.net}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DMG="$HERE/site/downloads/Friday-$VERSION.dmg"
[ -f "$DMG" ] || { echo "No $DMG: make the disk image first (release/make-dmg.sh)" >&2; exit 1; }
SHA="$(sha256sum "$DMG" 2>/dev/null || shasum -a 256 "$DMG")"
SHA="${SHA%% *}"
sed -e "s|@VERSION@|$VERSION|g" -e "s|@SHA256@|$SHA|g" -e "s|@SITE@|${SITE%/}|g" \
  "$HERE/release/install-template.sh" > "$HERE/site/install.sh"
echo "$HERE/site/install.sh"
