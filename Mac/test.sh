#!/bin/bash
# The Mac app's logic without a window: what each menu sends the page, where fridayd is looked for, the menu-bar
# label and which notifications are new.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
xcrun swiftc -swift-version 5 -target "$(uname -m)-apple-macos14.0" -sdk "$(xcrun --sdk macosx --show-sdk-path)" \
  Sources/HostAction.swift Sources/Server.swift Sources/MenuBarTimer.swift Sources/Notifier.swift Tests/main.swift \
  -o build/tests
build/tests
