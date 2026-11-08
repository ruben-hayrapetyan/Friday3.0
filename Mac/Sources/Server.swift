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
    nonisolated static let port = TestUser.current?.port ?? 8765  // Friday Test: its own (TestUser)
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
        out.append(home.appendingPathComponent("venvs/friday2.0/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/opt/homebrew/bin/fridayd"))
        out.append(URL(fileURLWithPath: "/usr/local/bin/fridayd"))
        return out
    }

    /// How `fridayd` is run: its executable, what goes before its own arguments, and what it adds to the environment.
    struct Launcher: Equatable {
        let executable: URL
        var prefix: [String] = []
        var settings: [String: String] = [:]
        var bundled = false

        /// The app's own Python reads nothing of yours: no PYTHONPATH or PYTHONHOME from a shell.
        func environment(_ base: [String: String]) -> [String: String] {
            var env = base
            if bundled { env["PYTHONPATH"] = nil; env["PYTHONHOME"] = nil }
            return env.merging(settings) { _, new in new }
        }
    }

    /// The Python inside the app (Mac/bundle.sh, HOSTED.md H109): Friday's server as anyone who downloads Friday has it.
    nonisolated static func bundledPython(resources: URL?, isExecutable: (String) -> Bool) -> URL? {
        guard let python = resources?.appendingPathComponent("friday/python/bin/python3.12"),
              isExecutable(python.path) else { return nil }
        return python
    }

    /// The app's own server as it's run: the planner compiled in the build is used (a generic Apple-silicon target,
    /// H111), nothing is written into the app (what more the planner compiles goes to ~/Library/Caches/Friday:
    /// server/planner_cache.py), and the data folder is chosen by `dataPlace`.
    /// It also passes its version, its place and the update feed's address when the build carries one (every build
    /// but Friday Test, H169), so the server can look for a newer Friday (commands/updates.py).
    nonisolated static func bundledLauncher(_ python: URL, home: URL, exists: (String) -> Bool,
                                            app: ThisApp? = nil) -> Launcher {
        let cache = home.appendingPathComponent("Library/Caches/Friday/planner").path
        var settings = ["NUMBA_CPU_NAME": "generic", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                        "NUMBA_CACHE_DIR": cache]
        if let app {
            settings["FRIDAY_APP_VERSION"] = app.version
            settings["FRIDAY_APP_PATH"] = app.path
            if let feed = app.feed { settings["FRIDAY_UPDATE_FEED"] = feed }
        }
        return Launcher(executable: python, prefix: ["-m", "friday.server.main"],
                        settings: settings.merging(dataPlace(home: home, exists: exists)) { a, _ in a }, bundled: true)
    }

    /// Where Friday keeps its data (H114, H115): a Friday already set up in ~/.local/share/friday stays there (yours);
    /// anyone new gets ~/Library/Application Support/Friday, with its friday.toml beside the data.
    nonisolated static func dataPlace(home: URL, exists: (String) -> Bool) -> [String: String] {
        if exists(home.appendingPathComponent(".local/share/friday/friday.db").path) { return [:] }
        let support = home.appendingPathComponent("Library/Application Support/Friday")
        return ["FRIDAY_DATA_DIR": support.path, "FRIDAY_CONFIG": support.appendingPathComponent("friday.toml").path]
    }

    /// This app as the updater needs it: its version, where it is, and the update feed if it's a downloaded copy.
    struct ThisApp: Equatable {
        let version: String
        let path: String
        let feed: String?

        static var running: ThisApp? {
            guard let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
            else { return nil }
            return ThisApp(version: version, path: Bundle.main.bundlePath,
                       feed: Bundle.main.object(forInfoDictionaryKey: "FridayUpdateFeed") as? String)
        }
    }

    /// The server to run: the one you chose in Settings, else the app's own, else one installed in the usual places.
    nonisolated static func launcher(chosen: String?, bundled: URL?, home: URL, isExecutable: (String) -> Bool,
                                     exists: (String) -> Bool, app: ThisApp? = nil) -> Launcher? {
        if let chosen, !chosen.isEmpty, isExecutable(chosen) { return Launcher(executable: URL(fileURLWithPath: chosen)) }
        if let bundled { return bundledLauncher(bundled, home: home, exists: exists, app: app) }
        return candidates(chosen: nil, home: home).first { isExecutable($0.path) }.map { Launcher(executable: $0) }
    }

    var launcher: Launcher? {
        let files = FileManager.default
        let isExecutable: (String) -> Bool = { files.isExecutableFile(atPath: $0) }
        return Self.launcher(chosen: UserDefaults.standard.string(forKey: "fridaydPath"),
                             bundled: Self.bundledPython(resources: Bundle.main.resourceURL, isExecutable: isExecutable),
                             home: files.homeDirectoryForCurrentUser, isExecutable: isExecutable,
                             exists: { files.fileExists(atPath: $0) }, app: ThisApp.running)
    }

    var executable: URL? { launcher?.executable }

    /// Running already (another copy, or `fridayd` started by hand), or start it.
    func ensureRunning(attempt: Int = 0) async {
        if await Self.status() != nil {
            await setUp()
            return
        }
        guard let launcher else {
            state = .failed("Friday's server, fridayd, wasn't found. Choose it in Settings → Mac app.")
            return
        }
        state = .starting
        let started = Process()
        Self.prepare(started, launcher, ["serve"])
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
            state = .failed(Self.startupWords(started: false, log: error.localizedDescription))
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
                state = .failed(Self.startupWords(started: true, log: log))
                return
            }
            try? await Task.sleep(for: .milliseconds(500))
        }
        state = .failed("Friday's server didn't answer within a minute. Your Mac may be very busy: wait a moment and "
            + "press Try again. If it keeps happening, quit Friday and open it again.\n\nWhat it said last:\n"
            + log.suffix(600))
    }

    /// Why the server stopped while starting, in words with what to do (8 Nov: "make all errors and warnings very
    /// user friendly so that they can debug it on the spot"), then what it said, for anyone who wants the detail.
    nonisolated static func startupWords(started: Bool, log: String) -> String {
        let said = log.lowercased()
        let detail = log.trimmingCharacters(in: .whitespacesAndNewlines)
        let what: String
        if said.contains("already in use") {
            what = "Another app is using Friday's port. Quit any other copy of Friday (or Friday Test), then press Try "
                + "again; if that doesn't free it, restart your Mac."
        } else if said.contains("database is locked") {
            what = "Friday's data is in use by another copy of Friday. Quit it, then press Try again."
        } else if said.contains("no space left") {
            what = "Your Mac's disk is full, so Friday can't save anything. Free some space, then press Try again."
        } else if said.contains("permission denied") || said.contains("operation not permitted") {
            what = "Friday isn't allowed to open its own files. In System Settings → Privacy & Security → Files and "
                + "Folders, let Friday in, then press Try again."
        } else if !started {
            what = "Friday's server couldn't be opened. Reinstall Friday from friday-scheduler.com, then open it again."
        } else {
            what = "Friday's server stopped while starting. Press Try again; if it happens again, write to "
                + "friday_support@friday-scheduler.com with \(detail.isEmpty ? "what happened" : "what's below")."
        }
        return detail.isEmpty ? what : what + "\n\nWhat it said:\n" + detail.suffix(600)
    }

    /// A server that isn't set up yet gets your time zone and personal's sleep times. Waited for off the main thread
    /// (the window kept drawing), and a setup that didn't take says so with Try again, rather than opening onto a
    /// Friday with no user.
    private func setUp() async {
        if let status = await Self.status(), status["ready"] as? Bool == false, let launcher {
            let init_ = Process()
            init_.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            Self.prepare(init_, launcher, ["init", "--timezone", TimeZone.current.identifier, "--bedtime", "23:30", "--wake", "07:30"])
            let code: Int32 = await withCheckedContinuation { done in
                init_.terminationHandler = { done.resume(returning: $0.terminationStatus) }
                do { try init_.run() } catch {
                    init_.terminationHandler = nil
                    done.resume(returning: -1)
                }
            }
            if code != 0, await Self.status()?["ready"] as? Bool == false {
                slow = false
                state = .failed("Friday couldn't set itself up for its first start. Press Try again; if it keeps "
                    + "happening, write to friday_support@friday-scheduler.com (it ended with code \(code)).")
                return
            }
        }
        slow = false
        state = .ready
    }

    /// `fridayd` with `subcommand`, run as `launcher` says: as it is for you; for Friday Test, in its user's folder
    /// on its port (its folder wins over the data folder `launcher` chose).
    nonisolated static func prepare(_ process: Process, _ launcher: Launcher, _ subcommand: [String],
                                    user: TestUser? = TestUser.current,
                                    base: [String: String] = ProcessInfo.processInfo.environment) {
        process.executableURL = launcher.executable
        var arguments = subcommand, environment = launcher.environment(base)
        if let user { (arguments, environment) = user.launch(subcommand, environment: environment) }
        process.arguments = launcher.prefix + arguments
        if user != nil || environment != base { process.environment = environment }
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
