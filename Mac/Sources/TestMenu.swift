import AppKit
import SwiftUI
import WebKit

/// Friday Test's own menu (TestUser): which user this is, starting over as a new one, and its folder.
struct TestMenu: Commands {
    var body: some Commands {
        CommandMenu("Test User") {
            if let user = TestUser.current {
                Text(user.name + (user.claude ? "" : ", without Claude"))
                Divider()
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

/// A new user from the very start: this one's server stopped, everything the window kept (looks, the tour seen, the
/// website's cache) cleared, a new folder and port, and the app opened again, so the launch is a first one. The old
/// user's folder stays, for a look afterwards.
@MainActor
enum StartOver {
    static func now(claude: Bool) {
        Server.shared.stop()
        TestUser.make(claude: claude)
        let store = WKWebsiteDataStore.default()  // this app's own: Friday Test's id, not yours
        store.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) {
            reopen()
        }
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
