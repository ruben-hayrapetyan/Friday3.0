import AppKit

/// Things 3, both ways (C108; the server's side is integrations/reminders.py Things), through Things' own AppleScript,
/// as Reminders goes through EventKit. Every twenty seconds the Mac app asks Friday whether Things is connected
/// (`reminder_writes` for kind things). Only then does it talk to Things, so macOS asks about Automation only after you
/// connect. It reads the open to-dos in Inbox, Today, Upcoming and Anytime (not Someday) while Things is open, at
/// most every ten minutes, and once at connect even if Things is closed; it ticks or unticks what you marked in Friday
/// while Things is open (until then they wait). Things missing from the Mac, or macOS saying no, is sent, so the box
/// says what to do.
@MainActor
final class ThingsBridge {
    nonisolated static let bundle = "com.culturedcode.ThingsMac"
    private var poll: Timer?
    private var busy = false
    private var lastRead: Date?
    private var lastSaid: Date?

    func start() {
        poll = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { _ in
            _ = Task { @MainActor in await self.tick() }
        }
        Task { await tick() }
    }

    private var running: Bool {
        !NSRunningApplication.runningApplications(withBundleIdentifier: Self.bundle).isEmpty
    }

    private func tick() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        guard let said = await Server.get("api/q/reminder_writes?kind=things") as? [String: Any] else { return }
        guard said["wanted"] as? Bool == true else {
            lastRead = nil  // connected again later: read afresh at once
            return
        }
        guard NSWorkspace.shared.urlForApplication(withBundleIdentifier: Self.bundle) != nil else {
            await tell(["missing": true])
            return
        }
        let due = lastRead.map { Date().timeIntervalSince($0) > 600 } ?? true
        if lastRead == nil || (running && due) {
            switch ThingsScript.read() {
            case .read(let todos):
                if await Server.post("reminders_sync", ["kind": "things", "reminders": todos, "lists": ThingsScript.lists]) != nil {
                    lastRead = Date()
                    lastSaid = nil
                }
            case .refused:
                await tell(["denied": true])
                return
            case .failed:
                return
            }
        }
        guard running else { return }  // what waits for Things waits until it's open
        for job in said["jobs"] as? [[String: Any]] ?? [] {
            let answer = TestUser.isTest ? ThingsScript.refuse(job) : ThingsScript.apply(job)
            if answer["id"] != nil { await Server.post("reminder_written", answer) }
        }
    }

    /// Said on the box, again every ten minutes in case it was cleared.
    private func tell(_ body: [String: Any]) async {
        guard lastSaid.map({ Date().timeIntervalSince($0) > 600 }) ?? true else { return }
        if await Server.post("reminders_sync", body.merging(["kind": "things"]) { a, _ in a }) != nil { lastSaid = Date() }
    }
}

/// Things' AppleScript: the to-dos of its lists in one go each, and a to-do ticked by its id.
enum ThingsScript {
    static let lists = ["Inbox", "Today", "Upcoming", "Anytime"]
    static let refusal = "Friday Test never changes your Things"

    enum Reading {
        case read([[String: Any]])
        case refused  // macOS said no to Automation (-1743)
        case failed
    }

    static func read() -> Reading {
        var seen = Set<String>()
        var out: [[String: Any]] = []
        for list in lists {
            let source = """
            tell application id "\(ThingsBridge.bundle)"
                set found to to dos of list "\(list)"
                return {id, name, notes, due date, activation date, status} of found
            end tell
            """
            var error: NSDictionary?
            guard let answer = NSAppleScript(source: source)?.executeAndReturnError(&error) else {
                // -1743: macOS said no to Automation; -1744: it would have to ask, and can't now
                return [-1743, -1744].contains(error?[NSAppleScript.errorNumber] as? Int) ? .refused : .failed
            }
            for todo in todos(answer, list: list) where seen.insert(todo["id"] as? String ?? "").inserted {
                out.append(todo)
            }
        }
        return .read(out)
    }

    /// {ids, names, notes, deadlines, when dates, statuses} as Friday's to-dos: the open ones, Today's before Anytime's.
    static func todos(_ answer: NSAppleEventDescriptor, list: String) -> [[String: Any]] {
        guard answer.numberOfItems == 6, let ids = answer.atIndex(1), ids.numberOfItems > 0 else { return [] }
        var out: [[String: Any]] = []
        for i in 1 ... ids.numberOfItems {
            let field = { (n: Int) in answer.atIndex(n)?.atIndex(i) }
            guard let id = field(1)?.stringValue, field(6).map(open) ?? true else { continue }
            var todo: [String: Any] = ["id": id, "title": field(2)?.stringValue ?? "", "notes": field(3)?.stringValue ?? "",
                                       "list": list, "completed": false]
            if let due = field(4).flatMap(day) { todo["due"] = due }
            if let when = field(5).flatMap(day) { todo["when"] = when }
            out.append(todo)
        }
        return out
    }

    /// Things' statuses come back as its enumeration's codes: open is 'tdio' (completed 'tdcm', canceled 'tdcl').
    static func open(_ status: NSAppleEventDescriptor) -> Bool {
        if status.descriptorType == typeEnumerated { return status.enumCodeValue == code("tdio") }
        return (status.stringValue ?? "open") == "open"
    }

    static func code(_ four: String) -> FourCharCode {
        four.utf8.reduce(0) { $0 << 8 | FourCharCode($1) }
    }

    /// A date as Friday reads a day ("2026-11-20"), on this Mac's calendar; missing value is none.
    static func day(_ d: NSAppleEventDescriptor) -> String? {
        guard d.descriptorType == typeLongDateTime, let date = d.dateValue else { return nil }
        return RemindersPayload.due(Calendar.current.dateComponents([.year, .month, .day], from: date))
    }

    static func refuse(_ job: [String: Any]) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        return ["id": id, "ok": false, "error": refusal]
    }

    static func apply(_ job: [String: Any]) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        guard let which = job["external_id"] as? String, let op = job["op"] as? String,
              op == "done" || op == "reopen", which.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "-" }) else {
            return ["id": id, "ok": false, "error": "Friday's change didn't say which to-do"]
        }
        let source = """
        tell application id "\(ThingsBridge.bundle)"
            set status of to do id "\(which)" to \(op == "done" ? "completed" : "open")
        end tell
        """
        var error: NSDictionary?
        guard NSAppleScript(source: source)?.executeAndReturnError(&error) != nil else {
            if (error?[NSAppleScript.errorNumber] as? Int) == -1728 { return ["id": id, "ok": true] }  // deleted since
            return ["id": id, "ok": false, "error": error?[NSAppleScript.errorMessage] as? String ?? "Things said no"]
        }
        return ["id": id, "ok": true]
    }
}
