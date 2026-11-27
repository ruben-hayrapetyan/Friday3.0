#!/bin/bash
# The Mac app's logic without a window: what each menu sends the page, where fridayd is looked for, the menu-bar
# label and the Dock's count of decisions.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
xcrun swiftc -swift-version 5 -target "$(uname -m)-apple-macos14.0" -sdk "$(xcrun --sdk macosx --show-sdk-path)" -framework EventKit \
  Sources/HostAction.swift Sources/FridayLink.swift Sources/SiriSays.swift Sources/Server.swift Sources/Launch.swift Sources/MenuBarTimer.swift Sources/DecisionsBadge.swift Sources/CalendarBridge.swift Sources/PlanCalendar.swift Sources/RemindersBridge.swift Sources/ThingsBridge.swift Sources/TestUser.swift Sources/Updater.swift Sources/PortChoice.swift Tests/main.swift \
  -o build/tests
# In the zone the tests are written for (27 Nov: on a Mac moved to Chicago, a whole day EventKit keeps in the Mac's
# zone read back a day early through the tests' New York calendar), as the web tests run in Alex's
TZ=America/New_York build/tests "$@"
