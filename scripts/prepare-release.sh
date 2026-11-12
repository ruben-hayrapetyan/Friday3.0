#!/bin/bash
# Prepares a version of Friday for release (HOSTED.md H123, H134, H136, H174): sets the version (VERSION and the
# same number in pyproject.toml, web/package.json and uv.lock) and commits it, builds the Mac app (without Google's
# client, C77), signs it with your Developer ID, makes the disk image, has Apple notarize it and staples the ticket
# to it (C88), and uploads it with its draft notes to the laptop. There it waits in
# the admin hub for you to edit and approve the notes and press
# Release. Nothing is released here.
#
#   scripts/prepare-release.sh VERSION NOTES.json
#
# NOTES.json: {"summary": "one sentence", "new": [lines], "changed": [lines], "fixed": [lines]} (H143).
# Where the hub is comes from ~/.config/friday/release.env, kept off git: FRIDAY_RELEASE_HOST (the machine over ssh)
# and FRIDAY_HUB_URL (its page). Signing (C88) uses the one "Developer ID Application" certificate in your keychain
# (or FRIDAY_SIGN_IDENTITY names one) and notarytool's keychain profile FRIDAY_NOTARY_PROFILE (friday-notary unless
# set): names only, the key and the certificate stay in your keychain. FRIDAY_PREPARE_APP names an app already built,
# so its test needn't build one.
set -euo pipefail

VERSION="${1:-}" NOTES="${2:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# The hub's whereabouts are private (C80): set in the environment, else in ~/.config/friday/release.env.
RELEASE_ENV="${FRIDAY_RELEASE_ENV:-$HOME/.config/friday/release.env}"
# shellcheck disable=SC1090
[ -f "$RELEASE_ENV" ] && . "$RELEASE_ENV"
HOST="${FRIDAY_RELEASE_HOST:-}"
die() { echo "Not prepared: $1" >&2; exit 1; }
[ -n "$HOST" ] || die "say where the hub is: FRIDAY_RELEASE_HOST in $RELEASE_ENV"

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
export FRIDAY_RELEASE=1  # downloads carry Friday's own app keys (Mac/app_keys.json): Trello, Microsoft, TickTick,
                        # Slack sign in for anyone (11 Nov); a release without the file says so and stops
[ -f "$REPO/Mac/app_keys.json" ] || { echo "No Mac/app_keys.json: downloads would have no Trello, Microsoft, TickTick or Slack" >&2; exit 1; }
cd "$REPO"
git diff --quiet HEAD -- || die "commit or set aside your changes first: a version is built from a commit"

# Every download is signed and notarized (C88, your choice: every prepare-release build): checked before the build,
# which takes minutes, so a missing certificate or profile is said at once.
IDENTITY="${FRIDAY_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  IDENTITY="$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: .*\)"$/\1/p' | sort -u)"
  [ -n "$IDENTITY" ] || die "no Developer ID Application certificate in your keychain (PROGRESS.md C88 says how to make one)"
  [ "$(printf '%s\n' "$IDENTITY" | wc -l | tr -d ' ')" = 1 ] \
    || die "more than one Developer ID Application certificate: name one in FRIDAY_SIGN_IDENTITY ($RELEASE_ENV)"
fi
PROFILE="${FRIDAY_NOTARY_PROFILE:-friday-notary}"
xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1 \
  || die "notarytool has no keychain profile '$PROFILE' that Apple accepts (PROGRESS.md C88 says how to store one)"

echo "==> Friday $VERSION"
# the number everywhere it's written (H174): VERSION, pyproject.toml, web/package.json and uv.lock
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

echo "==> Signing the app"
mkdir "$WORK/stage"
ditto "$APP" "$WORK/stage/Friday.app"  # keeps file times: the compiled planner inside is checked against them
Mac/sign.sh "$WORK/stage/Friday.app" "$IDENTITY" || die "the app couldn't be signed"

echo "==> Making the disk image"
ln -s /Applications "$WORK/stage/Applications"
DMG="$WORK/Friday-$VERSION.dmg"
hdiutil create -quiet -volname "Friday $VERSION" -srcfolder "$WORK/stage" -format ULFO -ov "$DMG"
codesign --sign "$IDENTITY" --timestamp "$DMG" || die "the disk image couldn't be signed"

echo "==> Notarizing (Apple checks it; usually a few minutes)"
# notarytool says Accepted or Invalid and exits 0 either way: the status is read, and Apple's reasons shown if not
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait --output-format json > "$WORK/notary.json" \
  || die "notarytool couldn't send it: $(cat "$WORK/notary.json")"
read -r NOTARY_ID NOTARY_STATUS < <(python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1]))
print(d.get("id", "?"), d.get("status", "?"))' "$WORK/notary.json")
if [ "$NOTARY_STATUS" != Accepted ]; then
  xcrun notarytool log "$NOTARY_ID" --keychain-profile "$PROFILE" >&2 || true
  die "Apple didn't notarize it ($NOTARY_STATUS, submission $NOTARY_ID): its reasons are above"
fi
xcrun stapler staple -q "$DMG" || die "the ticket couldn't be stapled to the disk image"
spctl --assess --type open --context context:primary-signature "$DMG" \
  || die "Gatekeeper doesn't accept the disk image"
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
echo "Friday $VERSION waits in the hub${FRIDAY_HUB_URL:+: $FRIDAY_HUB_URL}"
