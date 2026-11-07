import Foundation

/// Friday Test (29 Oct: "work on the startup sequence but I don't want to do this on my personal friday... assuming a
/// completely new user"): this app built by `build.sh --test`, a brand-new user's Friday beside yours and apart from it.
/// Its data and config in a folder of its own under ~/.local/share/friday-fresh (a new one each time it opens), its own
/// port, its own settings and website data (another app id), no global shortcuts (yours keeps them), never opened at
/// login, and it changes no real calendar: the Mac's are read and never written, and its server only reads Google's
/// (FRIDAY_CALENDARS_READ_ONLY). Your Friday, its data in ~/.local/share/friday and its server on 8765, isn't touched.
struct TestUser: Codable, Equatable {
    var folder: String  // its data in data/, its config (no keys, no Google) in config/
    var port: Int
    var claude: Bool  // false: a user without the `claude` command

    /// Whether this app is Friday Test: its Info.plist says so.
    static let isTest = Bundle.main.object(forInfoDictionaryKey: "FridayTest") as? Bool == true

    /// The user this app is: a new one each time it opens (29 Oct: "my version of friday test is not loading the
    /// initialization anymore": a user who had been through setup opened straight to the app), unless Keep This User
    /// Next Time is on and Start Over wasn't asked for. nil in your Friday.
    static let current: TestUser? = isTest ? opening() : nil

    /// Whether this run's user was made as the app opened: the window forgets the last one's looks and tour first.
    private(set) static var fresh = false

    static let key = "testUser"
    static let keepKey = "keepTestUser"  // Keep This User Next Time
    static let claudeKey = "testUserClaude"  // a new user has the `claude` command
    static let askedKey = "testUserAsked"  // Start Over, for the next opening
    static let updatedKey = "testUserUpdated"  // an update swapped in: the next opening keeps this user (HOSTED.md H146)
    static let keeping = 8  // test users' folders kept, the newest
    static let firstPort = 8770  // yours is 8765; scripts/fresh_user.sh's start at 8790
    static var root: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/share/friday-fresh")
    }

    var name: String { URL(fileURLWithPath: folder).lastPathComponent }
    var data: String { folder + "/data" }
    var config: String { folder + "/config/friday.toml" }

    static func kept(defaults: UserDefaults = .standard) -> TestUser? {
        defaults.data(forKey: key).flatMap { try? JSONDecoder().decode(TestUser.self, from: $0) }
    }

    /// The user an opening is: the kept one only when asked to keep it and not asked to start over; else a new one,
    /// with the `claude` command or without as last chosen, and the oldest test users' folders beyond `keeping` gone.
    static func opening(defaults: UserDefaults = .standard, root: URL = TestUser.root, isFree: (Int) -> Bool = TestUser.isFree) -> TestUser {
        let asked = defaults.bool(forKey: askedKey)
        let updated = defaults.bool(forKey: updatedKey)  // updating keeps the user, as it keeps your data
        defaults.removeObject(forKey: askedKey)
        defaults.removeObject(forKey: updatedKey)
        let keep = defaults.bool(forKey: keepKey) || updated
        if let kept = kept(defaults: defaults), !startsNew(keep: keep, asked: asked) { return kept }
        fresh = true
        let user = make(claude: defaults.object(forKey: claudeKey) as? Bool ?? true, root: root, defaults: defaults, isFree: isFree)
        for old in stale(in: root, keeping: keeping) { try? FileManager.default.removeItem(at: old) }
        return user
    }

    static func startsNew(keep: Bool, asked: Bool) -> Bool { asked || !keep }

    /// Friday Test's own users' folders (named mac-…, which sort by when) beyond the newest `keeping`, oldest first; a
    /// folder of scripts/fresh_user.sh's, or anything else there, is never one.
    static func stale(in root: URL, keeping: Int) -> [URL] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: root.path)) ?? []
        return names.filter { $0.hasPrefix("mac-") }.sorted().dropLast(keeping).map { root.appendingPathComponent($0) }
    }

    /// A new user, its folder made and kept as the one this app is from its next start.
    @discardableResult
    static func make(claude: Bool, root: URL = TestUser.root, now: Date = Date(), defaults: UserDefaults = .standard,
                     isFree: (Int) -> Bool = TestUser.isFree) -> TestUser {
        let stamp = DateFormatter()
        stamp.locale = Locale(identifier: "en_US_POSIX")
        stamp.dateFormat = "yyyy-MM-dd-HHmmss"
        let name = "mac-" + stamp.string(from: now)
        var folder = root.appendingPathComponent(name), n = 2
        while FileManager.default.fileExists(atPath: folder.path) {  // twice in one second
            folder = root.appendingPathComponent("\(name)-\(n)")
            n += 1
        }
        try? FileManager.default.createDirectory(at: folder.appendingPathComponent("config"), withIntermediateDirectories: true)
        let user = TestUser(folder: folder.path, port: freePort(from: firstPort, isFree: isFree), claude: claude)
        defaults.set(try? JSONEncoder().encode(user), forKey: key)
        return user
    }

    /// The first port from `start` nothing listens on, never yours.
    static func freePort(from start: Int, isFree: (Int) -> Bool = TestUser.isFree) -> Int {
        (start ..< 65535).first { $0 != 8765 && isFree($0) } ?? start
    }

    static func isFree(_ port: Int) -> Bool {
        let s = socket(AF_INET, SOCK_STREAM, 0)
        guard s >= 0 else { return false }
        defer { close(s) }
        var yes: Int32 = 1
        setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))  // as the server binds
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(UInt16(port).bigEndian)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        return withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(s, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
    }

    /// How `fridayd` runs for this user: its folder named twice over (the flag and the variables, which its config and
    /// plugins follow), its port, calendars read only, no AI key from the Mac's environment, and no `claude` if so chosen.
    func launch(_ subcommand: [String], environment: [String: String]) -> (arguments: [String], environment: [String: String]) {
        var env = environment.filter { !$0.key.hasSuffix("_API_KEY") && $0.key != "FRIDAY_AI_KEY" }
        env["FRIDAY_DATA_DIR"] = data
        env["FRIDAY_CONFIG"] = config
        env["FRIDAY_CALENDARS_READ_ONLY"] = "1"
        if claude { env["FRIDAY_CLAUDE"] = nil } else { env["FRIDAY_CLAUDE"] = "none" }
        let port = subcommand.first == "serve" ? ["--port", String(port)] : []
        return (["--data-dir", data] + subcommand + port, env)
    }
}

/// What Friday Test answers when Friday asks it to change one of the Mac's calendars: no, said so the status line
/// shows it ("Couldn't save … to your calendar").
enum TestCalendars {
    static let refusal = "Friday Test never changes this Mac's calendars"

    static func refuse(_ job: [String: Any]) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        return ["id": id, "ok": false, "error": refusal]
    }
}
