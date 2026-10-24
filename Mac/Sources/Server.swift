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
    nonisolated static let port = 8765
    nonisolated static var base: URL { URL(string: "http://127.0.0.1:\(port)/")! }

    @Published private(set) var state: State = .looking
    @Published private(set) var slow = false  // starting for a while: macOS may be asking for access
    private var process: Process?
    private var log = ""

    /// Where `fridayd` may be: what you chose in Settings, then the usual places.
    nonisolated static func candidates(chosen: String?, home: URL) -> [URL] {
        var out: [URL] = []
        if let chosen, !chosen.isEmpty { out.append(URL(fileURLWithPath: chosen)) }
        out.append(home.appendingPathComponent(".local/bin/fridayd"))
        out.append(home.appendingPathComponent("Downloads/Code/Friday-planner/.venv/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/opt/homebrew/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/usr/local/bin/fridayd"))
        return out
    }

    var executable: URL? {
        let chosen = UserDefaults.standard.string(forKey: "fridaydPath")
        return Self.candidates(chosen: chosen, home: FileManager.default.homeDirectoryForCurrentUser)
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    /// Running already (another copy, or `fridayd` started by hand), or start it.
    func ensureRunning(attempt: Int = 0) async {
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
        started.arguments = ["serve"]
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

    /// A server that isn't set up yet gets your time zone and personal's sleep times.
    private func setUp() async {
        if let status = await Self.status(), status["ready"] as? Bool == false, let executable {
            let init_ = Process()
            init_.executableURL = executable
            init_.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            init_.arguments = ["init", "--timezone", TimeZone.current.identifier, "--bedtime", "23:30", "--wake", "07:30"]
            try? init_.run()
            init_.waitUntilExit()
        }
        slow = false
        state = .ready
    }

    private func keep(_ text: String) {
        log = String((log + text).suffix(4000))
    }

    /// Stops the server only if this app started it.
    /// On quit: ask fridayd to stop and give it three seconds before insisting, so a Friday opened straight after
    /// finds the port free rather than "Friday's server isn't running".
    func stop() {
        guard let running = process else { return }
        process = nil
        running.terminate()
        let deadline = Date().addingTimeInterval(3)
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
