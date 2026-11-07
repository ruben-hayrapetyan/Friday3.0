import AppKit
import WebKit

/// Friday's own updater, the Mac half (HOSTED.md H120, H146, on rhayrapetyan/download-site). The server downloads a
/// new version, checks it and unpacks it into ~/Library/Caches/Friday/updates (commands/updates.py); the page then
/// tells the app here (`window.webkit.messageHandlers.friday`) to swap it in: right away, quitting and reopening, or
/// when you next quit, as Settings → Updates says. A small shell script does the swap once Friday has quit, since an
/// app can't replace itself while it runs; if the new one can't be moved in, the old one is put back.
@MainActor
final class Updater: NSObject, WKScriptMessageHandler {
    static let shared = Updater()
    private var atQuit: URL?

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let action = body["update"] as? String,
              let path = body["app"] as? String, let staged = Updater.accepted(path, cache: Updater.cache) else { return }
        switch action {
        case "install": install(staged, reopen: true)
        case "atQuit": atQuit = staged
        default: break
        }
    }

    /// When you quit: an update waiting for it goes in now and opens next time (H146).
    func quitting() {
        if let staged = atQuit { install(staged, reopen: false) }
    }

    private func install(_ staged: URL, reopen: Bool) {
        atQuit = nil
        if TestUser.isTest { UserDefaults.standard.set(true, forKey: TestUser.updatedKey) }  // the same test user after
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = Updater.swapArguments(pid: getpid(), app: Bundle.main.bundleURL, staged: staged, reopen: reopen)
        do { try process.run() } catch { return }
        if reopen { NSApp.terminate(nil) }
    }

    nonisolated static var cache: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/Friday/updates")
    }

    /// Only a Friday.app the server unpacked into the updates folder is ever swapped in, whatever the page sends.
    nonisolated static func accepted(_ path: String, cache: URL) -> URL? {
        let url = URL(fileURLWithPath: path).standardizedFileURL
        let folder = cache.standardizedFileURL.path + "/"
        guard url.lastPathComponent == "Friday.app", url.path.hasPrefix(folder) else { return nil }
        return url
    }

    nonisolated static func swapArguments(pid: Int32, app: URL, staged: URL, reopen: Bool) -> [String] {
        ["-c", swapScript, "friday-swap", String(pid), app.path, staged.path, reopen ? "1" : "0"]
    }

    /// Waits for Friday to quit, moves the old app aside, the new one in, and drops the old; reopens if asked.
    nonisolated static let swapScript = """
    pid="$1" app="$2" staged="$3" reopen="$4"
    while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
    aside="$app.replaced-$$"
    mv "$app" "$aside" || exit 1
    if mv "$staged" "$app"; then rm -r "$aside"; else mv "$aside" "$app"; fi
    if [ "$reopen" = 1 ]; then open "$app"; fi
    """
}
