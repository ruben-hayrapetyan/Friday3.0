#!/bin/bash
# A released version on GitHub, from the Mac (HOSTED.md H172–H175): tags the commit it was built from as vX.Y.Z and
# makes a GitHub Release with its notes and a link to the site for the download, from releases/released.json. The hub
# does this itself on Release once it has its token; this is for a version it couldn't, and for 0.2.0 and 0.3.0,
# released before it could (H175). Uses `gh`, signed in as you. A version already there is left as it is.
#
#   scripts/github-release.sh VERSION [--not-latest]
set -euo pipefail
VERSION="${1:-}" LATEST="${2:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
die() { echo "Not on GitHub: $1" >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "the version should be a number like 0.3.0, not '$VERSION'"
command -v gh >/dev/null || die "the GitHub command (gh) isn't installed: brew install gh, then gh auth login"
WORK="$(mktemp -d)"
trap 'rm -r "$WORK"' EXIT
python3 - "$REPO/releases/released.json" "$VERSION" "$WORK" "${FRIDAY_SITE_ADDRESS:-https://friday-scheduler.com}" <<'PY' || die "$VERSION isn't in releases/released.json with a commit: release it from the hub first"
import json, sys
record, version, work, address = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4]
found = next(v for v in record["versions"] if v["version"] == version and v.get("commit"))
notes = found["notes"]
lines = [notes["summary"], ""]
for key, title in (("new", "New"), ("changed", "Changed"), ("fixed", "Fixed")):
    if notes.get(key):
        lines += [f"### {title}", *[f"- {line}" for line in notes[key]], ""]
lines.append(f"Download Friday from {address.rstrip('/')}")
open(f"{work}/notes.md", "w").write("\n".join(lines))
open(f"{work}/commit", "w").write(found["commit"])
PY
cd "$REPO"
if gh release view "v$VERSION" >/dev/null 2>&1; then
    echo "Already on GitHub as v$VERSION."
    exit 0
fi
gh release create "v$VERSION" --target "$(cat "$WORK/commit")" --title "Friday $VERSION" \
    --notes-file "$WORK/notes.md" --latest="$([ "$LATEST" = "--not-latest" ] && echo false || echo true)"
echo "On GitHub as v$VERSION."
