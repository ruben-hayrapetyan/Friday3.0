import SwiftUI
import WebKit

/// The website, in the window (COMBINED.md 1): one UI for the Mac and the browser. Links to other sites open in your
/// browser; the menus and hotkeys reach the page through `HostAction`.
@MainActor
final class Page: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    static let shared = Page()
    let view: WKWebView
    private var loaded = false

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()  // keeps the look and other per-device settings between launches
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

    /// Anything not on Friday's own server opens in your browser.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != Server.base.host || url.port != Server.port {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    /// target="_blank" links, the same way.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
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

/// The window: the page once the server answers; until then, what's happening.
struct RootView: View {
    @ObservedObject var server = Server.shared

    var body: some View {
        Group {
            switch server.state {
            case .ready:
                WebPage()
            case .looking, .starting:
                VStack(spacing: 12) {
                    ProgressView()
                    Text(server.state == .starting ? "Starting Friday… the first start takes up to a minute." : "Finding Friday…")
                        .foregroundStyle(.secondary)
                    if server.slow {
                        // fridayd in ~/Downloads or ~/Documents waits on the Mac's privacy prompt until it's answered
                        Text("If macOS asks whether Friday may open files in a folder, allow it: that's where fridayd lives.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .failed(let why):
                VStack(spacing: 12) {
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
        .frame(minWidth: 1100, minHeight: 640)
    }
}
