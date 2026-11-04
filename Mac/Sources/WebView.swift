import SwiftUI
import WebKit

/// The website, in the window (COMBINED.md 1): one UI for the Mac and the browser. Links to other sites open in your
/// browser; the menus and hotkeys reach the page through `HostAction`. File pickers (a syllabus upload) and downloads
/// (a backup) need the app's own panels: WebKit on the Mac does nothing with them otherwise.
@MainActor
final class Page: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    static let shared = Page()
    let view: WKWebView
    private var loaded = false
    /// The app has drawn itself: the start's ring can close (`LaunchView`).
    @Published private(set) var shown = false

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()  // keeps the look and other per-device settings between launches
        config.applicationNameForUserAgent = "FridayMac"  // the page knows it's in the Mac app: the Mac's calendars come in here
        view = WKWebView(frame: .zero, configuration: config)
        view.isInspectable = true
        view.allowsBackForwardNavigationGestures = false
        super.init()
        view.navigationDelegate = self
        view.uiDelegate = self
    }

    func load() {
        guard !loaded else { return }
        loaded = true
        view.load(URLRequest(url: Server.base))
    }

    func send(_ action: HostAction) {
        view.evaluateJavaScript(action.script)
    }

    /// The page again from the server, past any cache (3 Nov: "cmd R did nothing"): a deploy's new web app at once.
    func reload() {
        view.reloadFromOrigin()
    }

    /// Anything not on Friday's own server opens in your browser.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != Server.base.host || url.port != Server.port {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(action.shouldPerformDownload ? .download : .allow)  // <a download>: the backup
    }

    /// A response the page can't show (sent as an attachment) is saved instead.
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping @MainActor (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    /// Where a download goes: you choose, starting in Downloads with the name the server gave it.
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping @MainActor (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.begin { answer in
            guard answer == .OK, let url = panel.url else { return completionHandler(nil) }
            try? FileManager.default.removeItem(at: url)  // the panel already asked about replacing it
            completionHandler(url)
        }
    }

    /// `<input type="file">`: the open panel, for the files the page asked for.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        let done: (NSApplication.ModalResponse) -> Void = { answer in
            completionHandler(answer == .OK ? panel.urls : nil)
        }
        if let window = webView.window { panel.beginSheetModal(for: window, completionHandler: done) } else { panel.begin(completionHandler: done) }
    }

    /// target="_blank" links, the same way.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    /// Loaded, then drawn: the page's script fills `#root` once React has run, a moment after the load itself.
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        waitForApp()
    }

    private func waitForApp(tries: Int = 0) {
        guard !shown else { return }
        view.evaluateJavaScript("(document.getElementById('root')?.childElementCount ?? 0) > 0") { [weak self] drawn, _ in
            guard let self else { return }
            if drawn as? Bool == true || tries >= 40 {  // four seconds at most: never kept from the app
                self.shown = true
            } else {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { self.waitForApp(tries: tries + 1) }
            }
        }
    }

    /// A page that failed to load (the server restarting) tries again shortly.
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        retry()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        retry()
    }

    private func retry() {
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
            view.load(URLRequest(url: Server.base))
        }
    }
}

struct WebPage: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView {
        Page.shared.load()
        return Page.shared.view
    }

    func updateNSView(_ view: WKWebView, context: Context) {}
}

/// The window: the app once it has drawn; until then, its icon filling while Friday starts (`LaunchView`), which
/// closes in gold and opens into the app. The page loads underneath the whole time, so it's there when it opens.
struct RootView: View {
    @ObservedObject var server = Server.shared
    @ObservedObject var page = Page.shared
    @State private var opened = false

    var body: some View {
        Group {
            if case .failed(let why) = server.state {
                failed(why)
            } else {
                ZStack {
                    if server.state == .ready { WebPage() }
                    if !opened {
                        LaunchView(state: server.state, slow: server.slow, ready: server.state == .ready && page.shown) {
                            opened = true
                        }
                    }
                }
            }
        }
        .frame(minWidth: 360, minHeight: 480)  // the website fits any width (web/src/shell/layout.ts)
    }

    private func failed(_ why: String) -> some View {
        VStack(spacing: 12) {
            FridayMark(size: 72, fill: 0.35, gold: 0).opacity(0.55).padding(.bottom, 6)
            Text("Friday's server isn't running").font(.title2)
            Text(why).font(.callout.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
            HStack {
                Button("Try again") { Task { await Server.shared.ensureRunning() } }
                SettingsLink { Text("Settings…") }
            }
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
