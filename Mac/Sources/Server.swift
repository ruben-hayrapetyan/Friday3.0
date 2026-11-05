import Foundation

/// `fridayd`, the server the Mac app shows (COMBINED.md 1, 2): found running, or started and kept for as long as the
/// app runs. Set up the first time with your time zone and personal's sleep times, which Settings can change.
@MainActor
final class Server: ObservableObject {
    enum State: Equatable {
        case looking
        case starting
        case ready
        case failed(String)
    }

    static let shared = Server()
    /// The server's Friday this app opens instead of starting its own (HOSTED.md S2, H77: Friday Test opens the
    /// server's staging copy), or nil: your Friday, which runs fridayd on this Mac. `build.sh --test` writes the
    /// address into Info.plist (FridayServer); `defaults write com.rubenhayrapetyan.friday.test hostedAddress URL`
    /// points it elsewhere, and `… hostedAddress local` gives Friday Test its own local user again.
    nonisolated static let remote: URL? = hostedAddress(
        plist: Bundle.main.object(forInfoDictionaryKey: "FridayServer") as? String,
        chosen: UserDefaults.standard.string(forKey: "hostedAddress"))
    nonisolated static let port = remote.map(effectivePort) ?? TestUser.current?.port ?? 8765  // Friday Test: its own
    nonisolated static var base: URL { remote ?? URL(string: "http://127.0.0.1:\(port)/")! }

    /// The address chosen in defaults, else the one built in; "local" (or nothing usable) means none.
    nonisolated static func hostedAddress(plist: String?, chosen: String?) -> URL? {
        let text = [chosen, plist].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.first { !$0.isEmpty }
        guard let text, text != "local", let url = URL(string: text.hasSuffix("/") ? text : text + "/"),
              url.scheme == "https" || url.scheme == "http", url.host != nil else { return nil }
        return url
    }

    nonisolated static func effectivePort(_ url: URL) -> Int { url.port ?? (url.scheme == "https" ? 443 : 80) }

    /// Whether a link stays in the window: Friday's own server, the same host and port; anything else opens in your
    /// browser.
    nonisolated static func isOwn(_ url: URL, base: URL = Server.base) -> Bool {
        url.host == base.host && effectivePort(url) == effectivePort(base)
    }

    @Published private(set) var state: State = .looking
    @Published private(set) var slow = false  // starting for a while: macOS may be asking for access
    private var process: Process?
    private var log = ""

    /// Where `fridayd` may be: what you chose in Settings, then the usual places.
    nonisolated static func candidates(chosen: String?, home: URL) -> [URL] {
        var out: [URL] = []
        if let chosen, !chosen.isEmpty { out.append(URL(fileURLWithPath: chosen)) }
        out.append(home.appendingPathComponent(".local/bin/fridayd"))
        out.append(home.appendingPathComponent("venvs/friday2.0/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/opt/homebrew/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/usr/local/bin/fridayd"))
        return out
    }

    var executable: URL? {
        let chosen = UserDefaults.standard.string(forKey: "fridaydPath")
        return Self.candidates(chosen: chosen, home: FileManager.default.homeDirectoryForCurrentUser)
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    /// Running already (another copy, or `fridayd` started by hand), or start it; the server's Friday is only
    /// looked for.
    func ensureRunning(attempt: Int = 0) async {
        if let remote = Self.remote { return await reach(remote) }
        if await Self.status() != nil {
            await setUp()
            return
        }
        guard let executable else {
            state = .failed("Friday's server, fridayd, wasn't found. Choose it in Settings → Mac app.")
            return
        }
        state = .starting
        let started = Process()
        started.executableURL = executable
        Self.prepare(started, ["serve"])
        started.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser  // not wherever the app was opened from
        let pipe = Pipe()
        started.standardOutput = pipe
        started.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let text = String(data: handle.availableData, encoding: .utf8) ?? ""
            Task { @MainActor in Server.shared.keep(text) }
        }
        do {
            try started.run()
        } catch {
            state = .failed("Couldn't start fridayd: \(error.localizedDescription)")
            return
        }
        process = started
        for tick in 0 ..< 120 {
            slow = tick >= 16  // its first start compiles the scheduler: up to a minute
            if await Self.status() != nil {
                await setUp()
                return
            }
            if !started.isRunning {
                // The Friday you just quit can take a few seconds to let go of the port; wait for it, then start.
                if log.contains("already in use"), attempt < 20 {
                    try? await Task.sleep(for: .seconds(1))
                    if await Self.status() != nil { return await setUp() }
                    log = ""
                    return await ensureRunning(attempt: attempt + 1)
                }
                state = .failed("fridayd stopped while starting:\n" + log.suffix(600))
                return
            }
            try? await Task.sleep(for: .milliseconds(500))
        }
        state = .failed("fridayd didn't answer within a minute:\n" + log.suffix(600))
    }

    /// The server's Friday, over Tailscale: up to ten seconds for it to answer, else why it may not have.
    private func reach(_ remote: URL) async {
        state = .looking
        for tick in 0 ..< 20 {
            slow = tick >= 6
            if await Self.status() != nil {
                slow = false
                state = .ready
                return
            }
            try? await Task.sleep(for: .milliseconds(500))
        }
        slow = false
        state = .failed("Couldn't reach Friday on the server at \(remote.absoluteString).\n"
                        + "Is Tailscale on and connected on this Mac?")
    }

    /// A server that isn't set up yet gets your time zone and personal's sleep times. Waited for off the main thread
    /// (the window kept drawing), and a setup that didn't take says so with Try again, rather than opening onto a
    /// Friday with no user.
    private func setUp() async {
        if let status = await Self.status(), status["ready"] as? Bool == false, let executable {
            let init_ = Process()
            init_.executableURL = executable
            init_.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            Self.prepare(init_, ["init", "--timezone", TimeZone.current.identifier, "--bedtime", "23:30", "--wake", "07:30"])
            let code: Int32 = await withCheckedContinuation { done in
                init_.terminationHandler = { done.resume(returning: $0.terminationStatus) }
                do { try init_.run() } catch {
                    init_.terminationHandler = nil
                    done.resume(returning: -1)
                }
            }
            if code != 0, await Self.status()?["ready"] as? Bool == false {
                slow = false
                state = .failed("Friday couldn't set itself up (fridayd init ended with \(code)).")
                return
            }
        }
        slow = false
        state = .ready
    }

    /// `fridayd` with `subcommand`: as it is for you; for Friday Test, in its user's folder on its port.
    nonisolated static func prepare(_ process: Process, _ subcommand: [String], user: TestUser? = TestUser.current) {
        guard let user else {
            process.arguments = subcommand
            return
        }
        let launch = user.launch(subcommand, environment: ProcessInfo.processInfo.environment)
        process.arguments = launch.arguments
        process.environment = launch.environment
    }

    private func keep(_ text: String) {
        log = String((log + text).suffix(4000))
    }

    /// Stops the server only if this app started it.
    /// On quit: ask fridayd to stop, and wait only until it has (about a quarter of a second since it ends its live
    /// streams at once), at most a second and a half before insisting, so a Friday opened straight after finds the
    /// port free rather than "Friday's server isn't running" (28 Oct: quitting took about three seconds).
    func stop() {
        guard let running = process else { return }
        process = nil
        running.terminate()
        let deadline = Date().addingTimeInterval(1.5)
        while running.isRunning, Date() < deadline { usleep(50_000) }
        if running.isRunning { kill(running.processIdentifier, SIGKILL) }
    }

    /// `/api/q/status`, or nil when nothing answers.
    nonisolated static func status() async -> [String: Any]? {
        await get("api/q/status") as? [String: Any]
    }

    nonisolated static func get(_ path: String) async -> Any? {
        guard let url = URL(string: path, relativeTo: base) else { return nil }  // keeps a ?query, unlike appendingPathComponent
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONSerialization.jsonObject(with: data)
    }

    @discardableResult
    nonisolated static func post(_ command: String, _ body: [String: Any] = [:]) async -> Any? {
        var request = URLRequest(url: base.appendingPathComponent("api/c/\(command)"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.setValue("mac", forHTTPHeaderField: "X-Friday-Client")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        request.timeoutInterval = 10
        guard let (data, _) = try? await URLSession.shared.data(for: request) else { return nil }
        return try? JSONSerialization.jsonObject(with: data)
    }
}
