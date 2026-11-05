import AppKit
import AuthenticationServices

/// Signing in through Apple's sign-in sheet over the window (HOSTED.md H95): the server's sign-in page in a browser
/// sheet that knows your passkeys, closing by itself when the server hands back `friday-test://signed-in?code=…`, with
/// no trip to your browser and no "Open Friday Test?" prompt. Your browser is the fallback when the sheet can't open.
@MainActor
final class SignInSheet: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?
    private let window: () -> NSWindow?

    init(window: @escaping () -> NSWindow?) {
        self.window = window
    }

    /// Opens the sheet on `url`; `done` gets the hand-back, or nil when you closed the sheet. False when it couldn't
    /// open. One sheet at a time: asked again while one is open, it stays as it is.
    func open(_ url: URL, scheme: String, done: @escaping @MainActor (URL?) -> Void) -> Bool {
        guard session == nil else { return true }
        let made = ASWebAuthenticationSession(url: url, callbackURLScheme: scheme) { [weak self] back, _ in
            Task { @MainActor in
                self?.session = nil
                done(back)
            }
        }
        made.presentationContextProvider = self
        made.prefersEphemeralWebBrowserSession = false  // the browser's passkeys and Google sign-in, as you left them
        session = made
        guard made.start() else {
            session = nil
            return false
        }
        return true
    }

    /// Signed in another way (the emailed link, in your browser): the sheet has nothing left to do.
    func close() {
        session?.cancel()
        session = nil
    }

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated { window() ?? ASPresentationAnchor() }
    }
}
