import AppKit
import SwiftUI
import WebKit

/// Friday Test's own menu (TestUser): which user this is, starting over as a new one, and its folder.
struct TestMenu: Commands {
    @AppStorage(TestUser.keepKey) private var keep = false

    var body: some Commands {
        CommandMenu("Test User") {
            if let user = TestUser.current {
                Text(user.name + (user.claude ? "" : ", without Claude"))
                Divider()
                Toggle("Keep This User Next Time", isOn: $keep)  // off: a new user each time Friday Test opens
                Button("Start Over as a New User") { StartOver.now(claude: true) }
                Button("Start Over as a New User without Claude") { StartOver.now(claude: false) }
                Divider()
                Button("Show Its Folder") {
                    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: user.folder)])
                }
            }
        }
    }
}

/// A new user from the very start: this one's server stopped and the app opened again, asked for a new user, so the
/// launch is a first one (`TestUser.opening`). The old user's folder stays, for a look afterwards.
@MainActor
enum StartOver {
    static func now(claude: Bool) {
        Server.shared.stop()
        UserDefaults.standard.set(true, forKey: TestUser.askedKey)
        UserDefaults.standard.set(claude, forKey: TestUser.claudeKey)
        reopen()
    }

    /// Everything the window kept for the last user (looks, the tour seen, the website's cache), cleared before a new
    /// user's page loads: this app's own website data, Friday Test's id, not yours.
    static func forget() async {
        await WKWebsiteDataStore.default().removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
    }

    /// Opens this app again once this copy has quit.
    private static func reopen() {
        let shell = Process()
        shell.executableURL = URL(fileURLWithPath: "/bin/sh")
        shell.arguments = ["-c", "while kill -0 \"$0\" 2>/dev/null; do sleep 0.1; done; exec open \"$1\"",
                           String(ProcessInfo.processInfo.processIdentifier), Bundle.main.bundlePath]
        try? shell.run()
        NSApp.terminate(nil)
    }
}
