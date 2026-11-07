#!/bin/sh
# Installs Friday on this Mac from the site, with no warning from macOS (HOSTED.md H131): run as
#   curl -fsSL @SITE@/install.sh | sh
# macOS checks only what a browser downloads, so Friday fetched here opens like any app. The disk image is checked
# against its checksum before anything is installed. Written by release/make-install.sh for each version.
#
# FRIDAY_INSTALL_DIR puts Friday somewhere other than /Applications (a Mac account that can't write there gets
# ~/Applications without it).
set -eu

VERSION="@VERSION@"
SHA256="@SHA256@"
URL="@SITE@/downloads/Friday-$VERSION.dmg"

fail() {
  printf '\nFriday wasn'"'"'t installed: %s\n' "$1" >&2
  exit 1
}

install_friday() {
  [ "$(uname -s)" = Darwin ] || fail "Friday is a Mac app for now."
  [ "$(uname -m)" = arm64 ] || fail "Friday needs a Mac with Apple silicon (M1 or newer)."
  major="$(sw_vers -productVersion | cut -d. -f1)"
  [ "$major" -ge 14 ] || fail "Friday needs macOS 14 or later; this Mac has $(sw_vers -productVersion)."

  target="${FRIDAY_INSTALL_DIR:-/Applications}"
  if [ -z "${FRIDAY_INSTALL_DIR:-}" ] && [ ! -w /Applications ]; then target="$HOME/Applications"; fi
  mkdir -p "$target" || fail "can't make $target."
  app="$target/Friday.app"
  if pgrep -f "$app/Contents/MacOS/Friday" >/dev/null 2>&1; then
    fail "Friday is open. Quit it (Friday → Quit Friday), then run this again. Your data stays as it is."
  fi

  work="$(mktemp -d)"
  mount="$work/disk"
  trap 'hdiutil detach -quiet "$mount" 2>/dev/null || true; rm -r "$work"' EXIT

  printf 'Downloading Friday %s (about 240 MB)...\n' "$VERSION"
  curl -fL --progress-bar -o "$work/Friday.dmg" "$URL" || fail "the download didn't finish. Try again."
  found="$(shasum -a 256 "$work/Friday.dmg" | cut -d' ' -f1)"
  [ "$found" = "$SHA256" ] || fail "the download isn't the file the site published (its checksum differs)."

  printf 'Installing it in %s...\n' "$target"
  hdiutil attach -quiet -nobrowse -readonly -mountpoint "$mount" "$work/Friday.dmg" </dev/null \
    || fail "the disk image wouldn't open."
  # beside the old copy first, so a failed copy leaves the Friday you have; file times kept (the compiled planner
  # inside is checked against them)
  ditto "$mount/Friday.app" "$app.new" || fail "couldn't copy Friday into $target."
  if [ -d "$app" ]; then rm -r "$app"; fi
  mv "$app.new" "$app"

  printf 'Friday %s is installed. Opening it...\n' "$VERSION"
  open "$app"
}

# Everything runs only once the whole script has arrived: a download cut short runs nothing.
install_friday
