import Foundation

/// When Friday's port is taken (19 Nov, a client: "Friday's server isn't running. Another app is using Friday's port",
/// most likely Anki's AnkiConnect, which listens on 8765 too). Who holds a port, from `lsof`; whether that's a Friday
/// server (one that doesn't answer is stopped, so a fresh one can start); else the next free port, kept for the next
/// launch, and told to the `friday` command (its cli.toml) as the server is told in its settings. Friday Test has its
/// own port (TestUser) and never moves into these.
enum PortChoice {
    static let standard = 8765
    static let defaultsKey = "fridayPort"  // where this app's server listens when 8765 was taken
    static let testPorts = 8770 ..< 8800  // Friday Test's (TestUser.firstPort) and scripts/fresh_user.sh's

    /// A process listening on a port, as `lsof -F pc` says it.
    struct Holder: Equatable {
        let pid: Int32
        let command: String
    }

    /// The listeners in `lsof -nP -iTCP:<port> -sTCP:LISTEN -Fpc` output: "p<pid>" then "c<command>" lines, a process
    /// once however many sockets it has (IPv4 and IPv6 each list it).
    static func holders(_ output: String) -> [Holder] {
        var out: [Holder] = []
        var pid: Int32?
        for line in output.split(whereSeparator: \.isNewline) {
            guard let tag = line.first else { continue }
            let value = String(line.dropFirst())
            if tag == "p" {
                pid = Int32(value)
            } else if tag == "c", let at = pid, !out.contains(where: { $0.pid == at }) {
                out.append(Holder(pid: at, command: value))
            }
        }
        return out
    }

    /// Whether a process is a Friday server, by its command line: `fridayd` (by hand, or under uv), or the server module
    /// as the app's bundled Python runs it ("python3.12 -m friday.server.main serve"). A web server someone else
    /// started, or Anki, is never one: only a Friday server is ever stopped.
    static func isFriday(arguments: String) -> Bool {
        let words = arguments.split(separator: " ").map(String.init)
        return words.contains { ($0 as NSString).lastPathComponent == "fridayd" } || words.contains("friday.server.main")
    }

    /// What a holder is called in a sentence: "Anki", or its command as `lsof` gives it.
    static func name(_ holder: Holder) -> String {
        let command = holder.command.trimmingCharacters(in: .whitespaces)
        if command.lowercased().hasPrefix("anki") { return "Anki" }
        return command.isEmpty ? "Another app" : command
    }

    /// The next port to use when `taken` isn't free: from the one after it, skipping 8765, Friday Test's ports and
    /// any not free; `taken` itself if none is (it then says what holds it).
    static func next(after taken: Int, isFree: (Int) -> Bool) -> Int {
        let candidates = Array((taken + 1) ..< 65535) + Array(8766 ..< max(8766, taken))
        return candidates.first { $0 != standard && !testPorts.contains($0) && isFree($0) } ?? taken
    }

    /// cli.toml with its `server` pointing at this Mac's port: added when missing, changed when it was this Mac's,
    /// left alone when you pointed it at another machine; the rest of the file kept as it was. nil: nothing to write.
    static func cliToml(_ text: String?, port: Int) -> String? {
        let url = "http://127.0.0.1:\(port)"
        var lines = (text ?? "").components(separatedBy: "\n")
        if let at = lines.firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("server") && $0.contains("=") }) {
            let was = lines[at].split(separator: "=", maxSplits: 1).last.map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
            let bare = was.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            guard bare.contains("://localhost:") || bare.contains("://127.0.0.1:") else { return nil }  // yours, elsewhere
            if bare == url { return nil }
            lines[at] = "server = \"\(url)\""
            return lines.joined(separator: "\n")
        }
        if port == standard { return nil }  // the command's own default already
        if (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "server = \"\(url)\"\n" }
        // a key at the top, before any [table], so TOML reads it as the file's own
        let header = lines.firstIndex { $0.trimmingCharacters(in: .whitespaces).hasPrefix("[") } ?? lines.count
        lines.insert("server = \"\(url)\"", at: header)
        let joined = lines.joined(separator: "\n")
        return joined.hasSuffix("\n") ? joined : joined + "\n"
    }

    // The Mac's own answers, kept apart from the decisions above so tests can give theirs.

    /// The processes listening on a port, as `lsof` sees them (yours alone, which is all Friday may stop).
    static func listening(on port: Int) -> [Holder] {
        holders(run("/usr/sbin/lsof", ["-nP", "-iTCP:\(port)", "-sTCP:LISTEN", "-Fpc"]))
    }

    /// A process's whole command line.
    static func arguments(of pid: Int32) -> String {
        run("/bin/ps", ["-o", "args=", "-p", String(pid)]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func run(_ path: String, _ arguments: [String]) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: path)
        process.arguments = arguments
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return "" }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return String(data: data, encoding: .utf8) ?? ""
    }

    /// Stops a Friday server that holds the port and doesn't answer: asked to stop, then made to, a few seconds in all.
    static func stop(_ pid: Int32, until free: () -> Bool) {
        kill(pid, SIGTERM)
        for _ in 0 ..< 30 where !free() { usleep(100_000) }
        if !free() {
            kill(pid, SIGKILL)
            for _ in 0 ..< 20 where !free() { usleep(100_000) }
        }
    }

    /// The `friday` command's settings file, pointed at this port (cliToml says when it's written).
    static func tellCommand(port: Int, file: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".config/friday/cli.toml")) {
        let text = try? String(contentsOf: file, encoding: .utf8)
        guard let updated = cliToml(text, port: port) else { return }
        try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? updated.write(to: file, atomically: true, encoding: .utf8)
    }
}
