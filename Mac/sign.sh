#!/bin/bash
# Signs Friday.app for downloading (PROGRESS.md C88): every compiled file in it with your Developer ID, under the
# hardened runtime and with a secure timestamp, as Apple's notarizing requires; innermost first, the app last.
#
#   Mac/sign.sh APP [IDENTITY]
#
# IDENTITY: the certificate's name, else FRIDAY_SIGN_IDENTITY, else the one "Developer ID Application" certificate in
# your keychain. "-" signs ad hoc under the hardened runtime, to try the app's entitlements on this Mac (no
# timestamp, not notarizable). Only names are used here: the certificate's key stays in your keychain.
set -euo pipefail

APP="${1:?usage: Mac/sign.sh APP [IDENTITY]}"
HERE="$(cd "$(dirname "$0")" && pwd)"
IDENTITY="${2:-${FRIDAY_SIGN_IDENTITY:-}}"
die() { echo "Not signed: $1" >&2; exit 1; }
[ -d "$APP/Contents/MacOS" ] || die "no app at $APP"

if [ -z "$IDENTITY" ]; then
  FOUND="$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: .*\)"$/\1/p' | sort -u)"
  [ -n "$FOUND" ] || die "no Developer ID Application certificate in your keychain (PROGRESS.md C88 says how to get one)"
  [ "$(printf '%s\n' "$FOUND" | wc -l | tr -d ' ')" = 1 ] || die "more than one Developer ID: name one in FRIDAY_SIGN_IDENTITY"
  IDENTITY="$FOUND"
fi
# quiet unless it fails ("replacing existing signature" for every file otherwise)
sign() { local said; said="$(codesign --force --sign "$IDENTITY" --options runtime "${STAMP[@]}" "$@" 2>&1)" || die "$said"; }

# Every Mach-O file, programs apart from libraries (the programs get entitlements), found by their first bytes.
LIST="$(mktemp)"
trap 'rm -f "$LIST" "$LIST".*' EXIT
PYTHON_ENTITLEMENTS="$HERE/entitlements/python.plist"
STAMP=(--timestamp)
if [ "$IDENTITY" = - ]; then
  # Ad hoc has no Team ID, and the hardened runtime loads only libraries of the program's own team: a try-out on this
  # Mac lets Python load them (a Developer ID signs them all with your team, so a download never needs this).
  STAMP=(--timestamp=none)
  PYTHON_ENTITLEMENTS="$LIST.plist"
  cp "$HERE/entitlements/python.plist" "$PYTHON_ENTITLEMENTS"
  /usr/libexec/PlistBuddy -c "Add :com.apple.security.cs.disable-library-validation bool true" "$PYTHON_ENTITLEMENTS"
fi
python3 -I - "$APP/Contents/Resources" "$LIST" <<'PY'
import os, struct, sys
programs, libraries = [], []
for root, _, files in os.walk(sys.argv[1]):
    for name in files:
        path = os.path.join(root, name)
        if os.path.islink(path):
            continue
        with open(path, "rb") as f:
            head = f.read(4096)
        if head[:4] == b"\xcf\xfa\xed\xfe":  # 64-bit, little-endian
            kind = struct.unpack("<I", head[12:16])[0]
        elif head[:4] == b"\xca\xfe\xba\xbe" and 0 < struct.unpack(">I", head[4:8])[0] < 8:  # universal (not Java)
            offset = struct.unpack(">I", head[16:20])[0]
            with open(path, "rb") as f:
                f.seek(offset)
                kind = struct.unpack("<I", f.read(16)[12:16])[0]
        else:
            continue
        (programs if kind == 2 else libraries).append(path)  # MH_EXECUTE
open(sys.argv[2] + ".programs", "w").write("".join(p + "\0" for p in programs))
open(sys.argv[2] + ".libraries", "w").write("".join(p + "\0" for p in libraries))
print(f"    {len(libraries)} libraries, {len(programs)} programs")
PY

echo "==> Signing as ${IDENTITY}"
# One first, on its own: if macOS asks to use the certificate's key, it asks once ("Always Allow"), not once for each
# of eight signings already waiting (10 Nov: "there are still popups").
FIRST="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().split(b"\0")[0].decode())' "$LIST.libraries")"
[ -z "$FIRST" ] || sign "$FIRST"
# eight at a time; one that fails stops them all (xargs stops at an exit of 255) and is said
# shellcheck disable=SC2016  # the inner shell expands them
xargs -0 -P 8 -n 16 sh -c 'said="$(codesign --force --sign "$0" --options runtime '"${STAMP[*]}"' "$@" 2>&1)" \
  || { echo "$said" >&2; exit 255; }' "$IDENTITY" < "$LIST.libraries" || die "a library couldn't be signed"
while IFS= read -r -d '' program; do
  sign --entitlements "$PYTHON_ENTITLEMENTS" "$program"
done < "$LIST.programs"
sign --entitlements "$HERE/entitlements/app.plist" "$APP"
# --deep doesn't look in Resources, where the Python is: each of its files is checked too
xargs -0 -P 8 -n 32 codesign --verify --strict < "$LIST.libraries" || die "a library's signature doesn't check"
codesign --verify --deep --strict "$APP" || die "the signature doesn't check"
echo "    signed: $APP"
