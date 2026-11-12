#!/bin/bash
# Builds the Mac app around Friday's website (COMBINED.md 1, 5) with the Swift compiler from the Command Line Tools.
# Its hotkeys and live Dock icon (Shared/) came from the Swift app Friday grew out of. Friday's server,
# with its own Python, the website and the compiled planner, goes inside it (Mac/bundle.sh), so it runs on any
# Apple-silicon Mac as it is downloaded (HOSTED.md H108–H111).
#
#   ./build.sh                build into build/ for this Mac
#   ./build.sh --install      build, then replace /Applications/Friday.app and launch it (the switch, C11)
#   Every build but Friday Test looks for updates on the site (HOSTED.md H169): yours as a downloaded copy does.
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
# Friday's own app keys (Mac/app_keys.json: Trello, Microsoft, TickTick, Slack) go into Friday Test and downloads
# (11 Nov: "ship the keys in download"), never into your own Friday ("i don't want any of these accounts to be linked
# to my actual friday account"). Friday Test also carries Google's client, so Google Tasks can be tried there;
# downloads don't (C77: an unverified Google app lets in 100 people, ever).
if $TEST; then
  export FRIDAY_GOOGLE_CLIENT=1
elif [ "${FRIDAY_RELEASE:-}" != 1 ]; then
  export FRIDAY_NO_APP_KEYS=1
fi

cd "$(dirname "$0")"

APP_NAME="Friday"
EXECUTABLE="Friday"
# Its own id, so it runs beside the Swift app until the switch without sharing its settings or login item.
BUNDLE_ID="com.rubenhayrapetyan.friday.web"
VERSION="$(tr -d '[:space:]' < ../VERSION)"  # set by scripts/prepare-release.sh (HOSTED.md H136)
TEST_PLIST="" RIBBON=() FEED_PLIST="" SCHEME="friday"
# Every build but Friday Test looks at the site's feed (H169). Friday Test never does: the site's update is the regular
# Friday, which would open on your data.
if ! $TEST; then FEED_PLIST="<key>FridayUpdateFeed</key>       <string>https://friday-scheduler.com/updates.json</string>"; fi
# A practice update (scripts/practice-update.sh): Friday Test looks at a feed on this Mac offering Friday Test builds.
if $TEST && [ -n "${FRIDAY_PRACTICE_FEED:-}" ]; then
  FEED_PLIST="<key>FridayUpdateFeed</key>       <string>$FRIDAY_PRACTICE_FEED</string>"
fi
if $TEST; then
  # Another name and id: its own settings, website data and permissions, so macOS asks it as it would a new user.
  APP_NAME="Friday Test"
  EXECUTABLE="Friday Test"
  BUNDLE_ID="com.rubenhayrapetyan.friday.test"
  TEST_PLIST="<key>FridayTest</key>              <true/>"
  SCHEME="fridaytest"  # Friday's links (Mac/Sources/FridayLink.swift) stay yours; Friday Test answers to its own
  RIBBON=(--ribbon TEST)
fi

BUILD_DIR="build"
APP="$BUILD_DIR/$APP_NAME.app"
SHARED="Shared"  # the hotkeys and the live Dock icon, from the Swift app Friday grew out of
SOURCES=(Sources/*.swift "$SHARED/GlobalHotKey.swift" "$SHARED/FridayIcon.swift" "$SHARED/FridayCountdown.swift")
SDK="$(xcrun --sdk macosx --show-sdk-path)"
TARGET="$(uname -m)-apple-macos14.0"
SWIFTC=(xcrun swiftc)
# Siri's own commands (C131, Sources/FridayIntents.swift) need Xcode's App Intents metadata step: with Xcode on this
# Mac, Friday is compiled with its compiler and SDK, which also say what the step reads. Without it Friday builds the
# same, Siri's commands left out (its links still work); a release insists on it.
XCODE_DEV="${FRIDAY_XCODE:-/Applications/Xcode.app/Contents/Developer}"
TOOLCHAIN="$XCODE_DEV/Toolchains/XcodeDefault.xctoolchain"
INTENTS=false
if [ -x "$TOOLCHAIN/usr/bin/appintentsmetadataprocessor" ]; then
  INTENTS=true
  SDK="$XCODE_DEV/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
  SWIFTC=("$TOOLCHAIN/usr/bin/swiftc")
elif [ "${FRIDAY_RELEASE:-}" = 1 ]; then
  echo "A release needs Xcode for Siri's commands (C131): install it from the App Store, open it once, and build again." >&2
  exit 1
else
  echo "==> No Xcode here: building without Siri's own commands"
fi

echo "==> Cleaning"
[ -d "$APP" ] && rm -r "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> Compiling"
CONSTS=()
if $INTENTS; then
  # what the metadata step reads: the values of the App Intents types, as the compiler sees them
  printf '%s\n' '["AppIntent","EntityQuery","AppEntity","TransientEntity","AppEnum","AppShortcutProviding","AppShortcutsProvider","AnyResolverProviding","AppIntentsPackage","DynamicOptionsProvider"]' > "$BUILD_DIR/intent-protocols.json"
  CONSTS=(-emit-const-values-path "$BUILD_DIR/Friday.swiftconstvalues" -Xfrontend -const-gather-protocols-file -Xfrontend "$BUILD_DIR/intent-protocols.json")
fi
"${SWIFTC[@]}" -O -wmo -module-name Friday -swift-version 5 -target "$TARGET" -sdk "$SDK" \
  -framework WebKit -framework Carbon -framework EventKit -framework UserNotifications -framework ServiceManagement \
  "${SOURCES[@]}" ${CONSTS[@]+"${CONSTS[@]}"} -o "$APP/Contents/MacOS/$EXECUTABLE"

if $INTENTS; then
  echo "==> Siri's commands (App Intents metadata)"
  for f in "${SOURCES[@]}"; do echo "$PWD/$f"; done > "$BUILD_DIR/intent-sources.txt"
  echo "$PWD/$BUILD_DIR/Friday.swiftconstvalues" > "$BUILD_DIR/intent-consts.txt"
  XCODE_BUILD="$(/usr/libexec/PlistBuddy -c "Print :ProductBuildVersion" "$XCODE_DEV/../version.plist")"
  "$TOOLCHAIN/usr/bin/appintentsmetadataprocessor" --toolchain-dir "$TOOLCHAIN" --module-name Friday --sdk-root "$SDK" \
    --xcode-version "$XCODE_BUILD" --platform-family macOS --deployment-target 14.0 --target-triple "$TARGET" \
    --source-file-list "$BUILD_DIR/intent-sources.txt" --swift-const-vals-list "$BUILD_DIR/intent-consts.txt" \
    --output "$APP/Contents/Resources" --no-app-shortcuts-localization --force >/dev/null 2>"$BUILD_DIR/intents.txt" \
    || { cat "$BUILD_DIR/intents.txt" >&2; exit 1; }
  [ -f "$APP/Contents/Resources/Metadata.appintents/extract.actionsdata" ] || { echo "Siri's commands weren't written" >&2; exit 1; }
  rm "$BUILD_DIR/intent-protocols.json" "$BUILD_DIR/intent-sources.txt" "$BUILD_DIR/intent-consts.txt" "$BUILD_DIR/Friday.swiftconstvalues" "$BUILD_DIR/intents.txt"
fi

echo "==> Rendering app icon"
ICONSET="$BUILD_DIR/AppIcon.iconset"
"${SWIFTC[@]}" -swift-version 5 -target "$TARGET" -sdk "$SDK" \
  tools/MakeIcon/main.swift "$SHARED/FridayIcon.swift" "$SHARED/FridayCountdown.swift" -o "$BUILD_DIR/makeicon"
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
    <key>FridayBuild</key>               <string>$(date -u +%Y%m%dT%H%M%SZ)-$$</string>
    <key>LSMinimumSystemVersion</key>    <string>14.0</string>
    <key>LSApplicationCategoryType</key> <string>public.app-category.productivity</string>
    <key>NSHighResolutionCapable</key>   <true/>
    $TEST_PLIST
    $FEED_PLIST
    <key>NSAppTransportSecurity</key>
    <dict><key>NSAllowsLocalNetworking</key><true/></dict>
    <key>NSCalendarsFullAccessUsageDescription</key>
    <string>Friday plans around the calendars on this Mac and adds the events you make to the one you choose.</string>
    <key>NSRemindersFullAccessUsageDescription</key>
    <string>Friday plans your open reminders, once you connect Apple Reminders in Settings, and ticks them off when you finish them in Friday.</string>
    <key>CFBundleURLTypes</key>
    <array><dict>
      <key>CFBundleURLName</key><string>Friday link</string>
      <key>CFBundleURLSchemes</key><array><string>$SCHEME</string></array>
    </dict></array>
    <key>NSAppleEventsUsageDescription</key>
    <string>Friday reads your Things to-dos, once you connect Things in Settings, and ticks them off when you finish them in Friday.</string>
    <key>NSRemindersUsageDescription</key>
    <string>Friday plans your open reminders, once you connect Apple Reminders in Settings, and ticks them off when you finish them in Friday.</string>
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
