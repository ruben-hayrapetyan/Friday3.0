#!/bin/bash
# Builds the Mac app around Friday's website (COMBINED.md 1, 5) with the Swift compiler from the Command Line Tools.
# It reuses the Swift app's hotkeys and live Dock icon from UI/Sources/App rather than copying them. Friday's server,
# with its own Python, the website and the compiled planner, goes inside it (Mac/bundle.sh), so it runs on any
# Apple-silicon Mac as it is downloaded (HOSTED.md H108–H111).
#
#   ./build.sh                build into build/ for this Mac
#   ./build.sh --install      build, then replace /Applications/Friday.app and launch it (the switch, C11)
#   ./build.sh --test [--open]  Friday Test, a brand-new user's Friday beside yours (Sources/TestUser.swift), into
#                               build/ only: never /Applications. --open opens it.
set -euo pipefail

INSTALL=false TEST=false OPEN=false
for arg in "$@"; do
  case "$arg" in
    --install) INSTALL=true ;;
    --test) TEST=true ;;
    --open) OPEN=true ;;
    *) echo "usage: $0 [--install | --test [--open]]" >&2; exit 2 ;;
  esac
done
if $TEST && $INSTALL; then echo "Friday Test stays in build/: no --install" >&2; exit 2; fi

cd "$(dirname "$0")"

APP_NAME="Friday"
EXECUTABLE="Friday"
# Its own id, so it runs beside the Swift app until the switch without sharing its settings or login item.
BUNDLE_ID="com.rubenhayrapetyan.friday.web"
VERSION="$(tr -d '[:space:]' < ../VERSION)"  # set by scripts/prepare-release.sh (HOSTED.md H136)
TEST_PLIST="" RIBBON=()
if $TEST; then
  # Another name and id: its own settings, website data and permissions, so macOS asks it as it would a new user.
  APP_NAME="Friday Test"
  EXECUTABLE="Friday Test"
  BUNDLE_ID="com.rubenhayrapetyan.friday.test"
  TEST_PLIST="<key>FridayTest</key>              <true/>"
  RIBBON=(--ribbon TEST)
fi

BUILD_DIR="build"
APP="$BUILD_DIR/$APP_NAME.app"
SHARED="../UI/Sources/App"
SOURCES=(Sources/*.swift "$SHARED/GlobalHotKey.swift" "$SHARED/FridayIcon.swift" "$SHARED/FridayCountdown.swift")
SDK="$(xcrun --sdk macosx --show-sdk-path)"
TARGET="$(uname -m)-apple-macos14.0"

echo "==> Cleaning"
[ -d "$APP" ] && rm -r "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> Compiling"
xcrun swiftc -O -swift-version 5 -target "$TARGET" -sdk "$SDK" \
  -framework WebKit -framework Carbon -framework EventKit -framework UserNotifications -framework ServiceManagement \
  "${SOURCES[@]}" -o "$APP/Contents/MacOS/$EXECUTABLE"

echo "==> Rendering app icon"
ICONSET="$BUILD_DIR/AppIcon.iconset"
xcrun swiftc -swift-version 5 -target "$TARGET" -sdk "$SDK" \
  ../UI/tools/MakeIcon/main.swift "$SHARED/FridayIcon.swift" "$SHARED/FridayCountdown.swift" -o "$BUILD_DIR/makeicon"
"$BUILD_DIR/makeicon" "$ICONSET" ${RIBBON[@]+"${RIBBON[@]}"} >/dev/null
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -r "$ICONSET" "$BUILD_DIR/makeicon"

echo "==> Writing Info.plist"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>       <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>        <string>$EXECUTABLE</string>
    <key>CFBundleIdentifier</key>        <string>$BUNDLE_ID</string>
    <key>CFBundleIconFile</key>          <string>AppIcon</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key>           <string>$VERSION</string>
    <key>LSMinimumSystemVersion</key>    <string>14.0</string>
    <key>LSApplicationCategoryType</key> <string>public.app-category.productivity</string>
    <key>NSHighResolutionCapable</key>   <true/>
    $TEST_PLIST
    <key>NSAppTransportSecurity</key>
    <dict><key>NSAllowsLocalNetworking</key><true/></dict>
    <key>NSCalendarsFullAccessUsageDescription</key>
    <string>Friday plans around the calendars on this Mac and adds the events you make to the one you choose.</string>
</dict>
</plist>
PLIST
printf 'APPL????' > "$APP/Contents/PkgInfo"

echo "==> Building the website"
(cd ../web && npx --yes pnpm@10.12.1 build >/dev/null)
./bundle.sh "$APP"

echo "==> Signing (ad-hoc)"
codesign --force --sign - --timestamp=none "$APP"
touch "$APP"
echo "==> Built $APP"
if $OPEN; then open "$APP"; fi

if $INSTALL; then
  echo "==> Installing to /Applications"
  osascript -e 'tell application id "com.rubenhayrapetyan.friday" to quit' 2>/dev/null || true
  osascript -e "tell application id \"$BUNDLE_ID\" to quit" 2>/dev/null || true
  # Quitting stops its server first, which can take a while; opening while it's still going fails (30 Oct: error -600)
  for _ in {1..150}; do
    pgrep -f "/Applications/$APP_NAME.app/" >/dev/null || break
    sleep 0.1
  done
  [ -d "/Applications/$APP_NAME.app" ] && rm -r "/Applications/$APP_NAME.app"
  ditto "$APP" "/Applications/$APP_NAME.app"  # keeps file times: the compiled planner is checked against them
  for _ in 1 2 3; do
    open "/Applications/$APP_NAME.app" && break
    sleep 2
  done
  echo "==> Installed and launched /Applications/$APP_NAME.app"
fi
