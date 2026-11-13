import EventKit
import Foundation

// A plain executable rather than XCTest, like UI/Tests: runs with only the Command Line Tools. Run ./test.sh.

var failures = 0

func check(_ condition: @autoclosure () -> Bool, _ message: String, line: UInt = #line) {
    if !condition() {
        failures += 1
        print("  ✘ \(message)  (line \(line))")
    }
}

func test(_ name: String, _ body: () -> Void) {
    print("• \(name)")
    body()
}

/// What the page receives: the event's detail, parsed back out of the script.
func detail(_ action: HostAction) -> [String: String]? {
    let script = action.script
    guard script.hasPrefix("window.dispatchEvent(new CustomEvent('friday:host', { detail: "),
          let open = script.firstIndex(of: "{"), let start = script[script.index(after: open)...].firstIndex(of: "{"),
          let end = script.lastIndex(of: "}") else { return nil }
    let json = script[start ..< script.index(before: end)].trimmingCharacters(in: .whitespaces)
    return (try? JSONSerialization.jsonObject(with: Data(json.utf8))) as? [String: String]
}

test("every action reaches the page as a friday:host event with its name") {
    let all: [(HostAction, String)] = [
        (.newEvent, "newEvent"), (.newTodo, "newTodo"), (.search, "search"), (.askClaude, "ask"), (.today, "today"),
        (.previous, "previous"), (.next, "next"), (.drawer, "drawer"), (.otherWays, "ways"), (.shove, "shove"),
        (.pace, "pace"), (.brief, "brief"), (.triage, "triage"), (.tour, "tour"), (.setup, "setup"),
    ]
    for (action, name) in all {
        check(detail(action) == ["action": name], "\(action) sends \(String(describing: detail(action)))")
    }
}

test("a view or a page goes with its argument") {
    check(detail(.view("month")) == ["action": "view", "argument": "month"], "view month")
    check(detail(.go("/settings")) == ["action": "go", "argument": "/settings"], "go settings")
    check(detail(.go("/")) == ["action": "go", "argument": "/"], "go plan")
    check(detail(.openDrawer) == ["action": "drawer", "argument": "open"], "the summon hotkey opens the drawer")
}

test("an argument can't break out of the script") {
    let sneaky = HostAction.go("'); alert(1); ('\" </script>")
    check(detail(sneaky)?["argument"] == "'); alert(1); ('\" </script>", "quoted as JSON: \(sneaky.script)")
}

test("fridayd: what you chose first, then the usual places") {
    let home = URL(fileURLWithPath: "/Users/someone")
    let found = Server.candidates(chosen: "/opt/friday/fridayd", home: home).map(\.path)
    check(found.first == "/opt/friday/fridayd", "chosen first: \(found)")
    check(found.contains("/Users/someone/.local/bin/fridayd"), "uv tool install's place")
    check(found.contains("/Users/someone/venvs/friday2.0/bin/fridayd"), "the checkout")
    check(Server.candidates(chosen: "", home: home).first == home.appendingPathComponent(".local/bin/fridayd"),
          "an empty choice is no choice")
    check(Server.candidates(chosen: nil, home: home).count == 4, "four usual places")
}

test("the server inside the app: chosen in Settings first, then the app's own, then the usual places (H109)") {
    let home = URL(fileURLWithPath: "/Users/someone")
    let resources = URL(fileURLWithPath: "/Applications/Friday.app/Contents/Resources")
    let python = "/Applications/Friday.app/Contents/Resources/friday/python/bin/python3.12"
    let bundled = Server.bundledPython(resources: resources, isExecutable: { $0 == python })
    check(bundled?.path == python, "the app's own Python")
    check(Server.bundledPython(resources: resources, isExecutable: { _ in false }) == nil, "an app built without one")
    let everything: (String) -> Bool = { _ in true }
    let own = Server.launcher(chosen: nil, bundled: bundled, home: home, isExecutable: everything, exists: { _ in false })
    check(own?.executable.path == python && own?.prefix == ["-m", "friday.server.main"] && own?.bundled == true,
          "nothing chosen: the app's own, run as a module")
    let chosen = Server.launcher(chosen: "/opt/fridayd", bundled: bundled, home: home, isExecutable: everything,
                                 exists: { _ in false })
    check(chosen == Server.Launcher(executable: URL(fileURLWithPath: "/opt/fridayd")), "what you chose wins")
    let gone = Server.launcher(chosen: "/opt/gone", bundled: nil, home: home, isExecutable: { $0 != "/opt/gone" },
                               exists: { _ in false })
    check(gone?.executable.path == "/Users/someone/.local/bin/fridayd", "a choice that's gone, no app's own: installed")
    check(Server.launcher(chosen: nil, bundled: nil, home: home, isExecutable: { _ in false }, exists: { _ in false })
          == nil, "none anywhere: nil, and the window says so")
}

test("the app's own server: the shipped planner as it is, nothing written into the app, nothing of a shell's Python") {
    let home = URL(fileURLWithPath: "/Users/someone")
    let python = URL(fileURLWithPath: "/Applications/Friday.app/Contents/Resources/friday/python/bin/python3.12")
    let own = Server.bundledLauncher(python, home: home, exists: { _ in false })
    let env = own.environment(["PATH": "/usr/bin", "PYTHONPATH": "/Users/someone/src", "PYTHONHOME": "/x"])
    check(env["NUMBA_CPU_NAME"] == "generic", "the planner compiled for any Apple silicon (H111)")
    check(env["NUMBA_CACHE_DIR"] == "/Users/someone/Library/Caches/Friday/planner",
          "what the planner compiles more goes to Caches, never into the app: \(env["NUMBA_CACHE_DIR"] ?? "")")
    check(env["PYTHONDONTWRITEBYTECODE"] == "1" && env["PYTHONNOUSERSITE"] == "1", "writes nothing, reads no user site")
    check(env["PYTHONPATH"] == nil && env["PYTHONHOME"] == nil && env["PATH"] == "/usr/bin", "a shell's Python left out")
    let process = Process()
    Server.prepare(process, own, ["serve"], user: nil, base: ["PATH": "/usr/bin"])
    check(process.arguments == ["-m", "friday.server.main", "serve"], "\(process.arguments ?? [])")
    let test = Process()
    Server.prepare(test, own, ["serve"], user: TestUser(folder: "/tmp/f", port: 8770, claude: true), base: [:])
    check(test.arguments == ["-m", "friday.server.main", "--data-dir", "/tmp/f/data", "serve", "--port", "8770"],
          "Friday Test on the app's own Python, in its folder: \(test.arguments ?? [])")
    check(test.environment?["FRIDAY_DATA_DIR"] == "/tmp/f/data", "its folder wins over the new user's place")
}

test("where Friday keeps its data: yours where it is, anyone new in Application Support (H114, H115)") {
    let home = URL(fileURLWithPath: "/Users/someone")
    check(Server.dataPlace(home: home, exists: { $0 == "/Users/someone/.local/share/friday/friday.db" }) == [:],
          "a Friday already set up in ~/.local/share/friday stays there")
    let fresh = Server.dataPlace(home: home, exists: { _ in false })
    check(fresh["FRIDAY_DATA_DIR"] == "/Users/someone/Library/Application Support/Friday", "new: Application Support")
    check(fresh["FRIDAY_CONFIG"] == "/Users/someone/Library/Application Support/Friday/friday.toml",
          "its friday.toml beside the data")
}

test("the server is on this Mac only") {
    check(Server.base.absoluteString == "http://127.0.0.1:8765/", "base \(Server.base)")
    check(URL(string: "api/q/item?id=3", relativeTo: Server.base)?.absoluteString == "http://127.0.0.1:8765/api/q/item?id=3",
          "a query survives")
}

test("the menu-bar label") {
    check(MenuBarTimer.label(title: "Essay", seconds: 0) == "● Essay 0:00", "zero")
    check(MenuBarTimer.label(title: "Essay", seconds: 59.9) == "● Essay 0:59", "rounds down")
    check(MenuBarTimer.label(title: "Essay", seconds: 3599) == "● Essay 59:59", "under an hour")
    check(MenuBarTimer.label(title: "Essay", seconds: 3723) == "● Essay 1:02:03", "over an hour")
    check(MenuBarTimer.label(title: "Essay", seconds: -5) == "● Essay 0:00", "a clock that ran back")
    let long = MenuBarTimer.label(title: "Problem set 7 for linear algebra", seconds: 61)
    check(long == "● Problem set 7 for linea… 1:01", "a long title is cut: \(long)")
    check(MenuBarTimer.label(title: String(repeating: "x", count: 24), seconds: 0).contains(String(repeating: "x", count: 24)),
          "24 characters fit")
}

test("the Dock counts the decisions waiting in the Inbox, and shows nothing when none wait") {
    check(DecisionsBadge.label(["decisions": [["key": "late"], ["key": "lock:-1509"]]]) == "2", "two")
    check(DecisionsBadge.label(["decisions": []]) == nil, "none")
    check(DecisionsBadge.label([:]) == nil, "an older server without decisions")
}

test("calendar payload: one id per occurrence") {
    let monday = Date(timeIntervalSince1970: 1_792_504_800)  // 2026-10-20 10:00 New York
    let week = monday.addingTimeInterval(7 * 86400)
    check(MacPayload.occurrenceID("abc", at: monday) != MacPayload.occurrenceID("abc", at: week), "differ by occurrence")
    check(MacPayload.occurrenceID("abc", at: monday) == MacPayload.occurrenceID("abc", at: monday), "stable")
}

test("calendar payload: times with the Mac's offset") {
    let monday = Date(timeIntervalSince1970: 1_792_504_800)
    let york = TimeZone(identifier: "America/New_York")!
    check(MacPayload.timestamp(monday, zone: york) == "2026-10-20T10:00:00-04:00", MacPayload.timestamp(monday, zone: york))
    let november = monday.addingTimeInterval(14 * 86400)  // after the clocks change
    check(MacPayload.timestamp(november, zone: york) == "2026-11-03T09:00:00-05:00", MacPayload.timestamp(november, zone: york))
    check(MacPayload.timestamp(monday, zone: TimeZone(identifier: "UTC")!) == "2026-10-20T14:00:00+00:00", "UTC spelled as an offset")
}

test("calendar payload: whole days end the day after the last") {
    var york = Calendar(identifier: .gregorian)
    york.timeZone = TimeZone(identifier: "America/New_York")!
    let start = york.date(from: DateComponents(year: 2026, month: 10, day: 22))!
    let lastSecond = york.date(from: DateComponents(year: 2026, month: 10, day: 23, hour: 23, minute: 59, second: 59))!
    check(MacPayload.day(MacPayload.allDayEnd(start: start, end: lastSecond, calendar: york), calendar: york) == "2026-10-24",
          "EventKit's 23:59:59 end")
    let nextMidnight = york.date(from: DateComponents(year: 2026, month: 10, day: 24))!
    check(MacPayload.day(MacPayload.allDayEnd(start: start, end: nextMidnight, calendar: york), calendar: york) == "2026-10-24",
          "an end already at midnight")
    check(MacPayload.day(MacPayload.allDayEnd(start: start, end: start, calendar: york), calendar: york) == "2026-10-23",
          "a zero-length one is still a day")
    check(MacPayload.day(start, calendar: york) == "2026-10-22", "the day")
}

test("calendar payload: types and colours") {
    check(MacPayload.typeName(.calDAV) == "caldav" && MacPayload.typeName(.birthday) == "birthday", "types")
    check(MacPayload.typeName(.subscription) == "subscription" && MacPayload.typeName(.local) == "local", "more types")
    check(MacPayload.hex(red: 0.227, green: 0.353, blue: 0.549) == "#3a5a8c", MacPayload.hex(red: 0.227, green: 0.353, blue: 0.549))
    check(MacPayload.hex(red: 1.2, green: -0.1, blue: 1) == "#ff00ff", "clamped")
}

test("calendar payload: the body mac_sync takes") {
    let since = Date(timeIntervalSince1970: 1_792_382_400)  // 2026-10-19 00:00 New York
    let body = MacPayload.body(calendars: [["id": "c", "name": "Home"]], events: [], since: since, until: since.addingTimeInterval(86400))
    check(Set(body.keys) == ["calendars", "events", "since", "until"], "\(body.keys)")
    check((body["since"] as? String)?.count == 25, "since with an offset: \(body["since"] ?? "")")
    if CommandLine.arguments.count > 1 {  // ./test.sh payload.json writes a sample for the server's test
        let monday = Date(timeIntervalSince1970: 1_792_504_800)
        let sample = MacPayload.body(
            calendars: [["id": "home-id", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c", "writable": true]],
            events: [["id": MacPayload.occurrenceID("dentist", at: monday), "calendar": "home-id", "title": "Dentist",
                      "start": MacPayload.timestamp(monday), "end": MacPayload.timestamp(monday.addingTimeInterval(3600)),
                      "all_day": false, "free": false, "declined": false]],
            since: since, until: since.addingTimeInterval(12 * 7 * 86400))
        let data = try! JSONSerialization.data(withJSONObject: sample, options: [.sortedKeys])
        try! data.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
    }
}

test("a change Friday asks of a Mac event: which occurrence, and what it changes") {
    var york = Calendar(identifier: .gregorian)
    york.timeZone = TimeZone(identifier: "America/New_York")!
    let (identifier, at) = MacWriter.parts("6F9619FF:abc@google.com@1761000000")!
    check(identifier == "6F9619FF:abc@google.com", "the identifier keeps its own @")
    check(Int(at.timeIntervalSince1970) == 1_761_000_000, "the occurrence's start")
    check(MacWriter.parts("no-occurrence") == nil && MacWriter.parts("x@later") == nil, "not an occurrence id")
    check(MacWriter.parts(MacPayload.occurrenceID("abc", at: Date(timeIntervalSince1970: 1_761_000_000)))!.0 == "abc", "round trip")

    let event = EKEvent(eventStore: EKEventStore())
    event.title = "Chem 2090 Lec (room 200)"
    event.startDate = Date(timeIntervalSince1970: 1_761_000_000)
    event.endDate = event.startDate.addingTimeInterval(3600)
    let later: [String: Any] = ["start": "2025-10-20T23:40:00Z", "end": "2025-10-21T00:40:00Z", "all_day": false]
    check(MacWriter.change(event, to: later), "moved")
    check(event.title == "Chem 2090 Lec (room 200)", "no title sent: the calendar's stays")
    check(Int(event.startDate.timeIntervalSince1970) == 1_761_003_600, "the new start \(event.startDate!)")
    check(!MacWriter.change(event, to: later), "the same again changes nothing")
    check(MacWriter.change(event, to: later.merging(["title": "Chem (moved to 120)"]) { $1 }), "renamed")
    check(event.title == "Chem (moved to 120)", "the new title")

    let day: [String: Any] = ["start": "2026-10-23", "end": "2026-10-24", "all_day": true]
    check(MacWriter.change(event, to: day, calendar: york) && event.isAllDay, "a whole day")
    check(MacPayload.day(event.startDate, calendar: york) == "2026-10-23", "starts that day")
    let end = MacPayload.allDayEnd(start: event.startDate, end: event.endDate, calendar: york)
    check(MacPayload.day(end, calendar: york) == "2026-10-24", "and reads back ending the day after, as Friday sent it")
    check(!MacWriter.change(event, to: day, calendar: york), "the same whole day again changes nothing")
    check(MacWriter.moment("2026-10-25T19:30:00Z", allDay: false) == Date(timeIntervalSince1970: 1_792_956_600), "a time")

    // Where it is (27 Oct): sent only when you changed it in Friday; "" takes it off.
    check(MacWriter.change(event, to: day.merging(["location": "Baker 200"]) { $1 }, calendar: york), "a place")
    check(event.location == "Baker 200", "the place")
    check(!MacWriter.change(event, to: day.merging(["location": "Baker 200"]) { $1 }, calendar: york), "the same place again")
    check(!MacWriter.change(event, to: day, calendar: york) && event.location == "Baker 200", "no place sent: it stays")
    check(MacWriter.change(event, to: day.merging(["location": ""]) { $1 }, calendar: york) && event.location == nil,
          "taken off")
}

test("new events Friday made are made once") {
    let defaults = UserDefaults(suiteName: "friday-tests-\(UUID().uuidString)")!
    let made = Made(defaults: defaults)
    check(made.event(for: 41) == nil, "nothing made yet")
    made.keep(41, occurrence: "ABC@1761000000", calendar: "gmail-cal")
    check(made.event(for: 41)?.occurrence == "ABC@1761000000" && made.event(for: 41)?.calendar == "gmail-cal", "kept")
    check(made.event(for: 42) == nil, "only that job's")
    let gone = MacWriter.apply(["id": 7, "op": "create", "calendar": "no-such-calendar", "title": "Salsa",
                                "start": "2026-10-30T22:15:00Z", "end": "2026-10-30T23:15:00Z"],
                               in: EKEventStore(), made: made)
    check(gone["ok"] as? Bool == false && (gone["error"] as? String ?? "").contains("isn't on this Mac"),
          "a calendar not on this Mac says so: \(gone)")
    let missing = MacWriter.apply(["id": 8, "op": "save", "calendar": "no-such-calendar", "event": "ABC@1761000000",
                                   "start": "2026-10-30T22:15:00Z", "end": "2026-10-30T23:15:00Z"],
                                  in: EKEventStore(), made: made)
    check(missing["ok"] as? Bool == false && missing["gone"] as? Bool == true,
          "a change to an event not found says it's gone, for Friday to make it again: \(missing)")
    for op in ["delete", "delete_from"] {
        let deleted = MacWriter.apply(["id": 9, "op": op, "calendar": "no-such-calendar", "event": "ABC@1761000000"],
                                      in: EKEventStore(), made: made)
        check(deleted["ok"] as? Bool == true, "\(op) of an event already gone is done: \(deleted)")
    }
}

test("the start's ring creeps while it waits, never closing on its own") {
    var last = 0.0
    for tenth in 0 ... 1200 {  // two minutes
        let at = LaunchCurve.frame(at: Double(tenth) / 10, readyAt: nil)
        check(at.fill >= last && at.fill < 0.92, "fill \(at.fill) at \(tenth)")
        check(at.gold == 0 && at.open == 0, "gold or open before ready at \(tenth)")
        last = at.fill
    }
    check(LaunchCurve.creep(1) > 0.3 && LaunchCurve.creep(3) > 0.6, "slow to start: \(LaunchCurve.creep(1)), \(LaunchCurve.creep(3))")
    check(LaunchCurve.creep(0) > 0, "the ring shows where it starts")
}

test("ready, it closes from where it was, turns gold, then opens, without a jump") {
    for ready in [0.2, 1.5, 9.0, 61.0] {
        let before = LaunchCurve.frame(at: ready, readyAt: nil)
        let at = LaunchCurve.frame(at: ready, readyAt: ready)
        check(abs(at.fill - before.fill) < 1e-9, "fill jumps when ready at \(ready)")
        let closed = LaunchCurve.frame(at: ready + LaunchCurve.fill, readyAt: ready)
        check(abs(closed.fill - 1) < 1e-9 && closed.open == 0, "closed but not yet open at \(ready)")
        let gold = LaunchCurve.frame(at: ready + LaunchCurve.goldAt + LaunchCurve.gold, readyAt: ready)
        check(gold.gold == 1 && gold.open == 0, "gold before opening at \(ready)")
        let shown = LaunchCurve.frame(at: ready + LaunchCurve.total, readyAt: ready)
        check(shown.open == 1 && shown.fill == 1, "open by the end at \(ready)")
        var last = LaunchCurve.Frame(fill: 0, gold: 0, open: 0)
        for step in 0 ... 100 {
            let f = LaunchCurve.frame(at: ready + LaunchCurve.total * Double(step) / 100, readyAt: ready)
            check(f.fill >= last.fill && f.gold >= last.gold && f.open >= last.open, "goes back at step \(step)")
            last = f
        }
    }
    check(LaunchCurve.total < 1.5, "the app waits \(LaunchCurve.total) s after it's ready")
    let inGold = LaunchCurve.openAt - (LaunchCurve.goldAt + LaunchCurve.gold)
    check(inGold >= 0.5 && inGold > LaunchCurve.fill, "the gold is held \(inGold) s, the close takes \(LaunchCurve.fill) s")
}

// Friday Test (TestUser): a new user's Friday beside yours.

func scratch() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("friday-test-\(UUID().uuidString)")
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

test("this is your Friday unless its Info.plist says Friday Test") {
    check(!TestUser.isTest && TestUser.current == nil, "the tests aren't Friday Test")
    check(Server.port == 8765, "yours stays on 8765: \(Server.port)")
}

test("a test user's server: its folder, its port, calendars read only, no keys") {
    let user = TestUser(folder: "/tmp/fresh/mac-1", port: 8771, claude: true)
    let mac = ["PATH": "/usr/bin", "HOME": "/Users/x", "ANTHROPIC_API_KEY": "sk-a", "OPENAI_API_KEY": "sk-o",
               "FRIDAY_AI_KEY": "k", "FRIDAY_CLAUDE": "/opt/claude", "FRIDAY_DATA_DIR": "/Users/x/.local/share/friday"]
    let serve = user.launch(["serve"], environment: mac)
    check(serve.arguments == ["--data-dir", "/tmp/fresh/mac-1/data", "serve", "--port", "8771"], "\(serve.arguments)")
    check(serve.environment["FRIDAY_DATA_DIR"] == "/tmp/fresh/mac-1/data", "your data folder replaced")
    check(serve.environment["FRIDAY_CONFIG"] == "/tmp/fresh/mac-1/config/friday.toml", "its own config")
    check(serve.environment["FRIDAY_CALENDARS_READ_ONLY"] == "1", "calendars read only")
    check(serve.environment.keys.allSatisfy { !$0.hasSuffix("_API_KEY") } && serve.environment["FRIDAY_AI_KEY"] == nil,
          "no key from the Mac's environment: \(serve.environment.keys.sorted())")
    check(serve.environment["FRIDAY_CLAUDE"] == nil, "with Claude: the usual claude command")
    check(serve.environment["PATH"] == "/usr/bin" && serve.environment["HOME"] == "/Users/x", "the rest kept")
    let without = TestUser(folder: "/tmp/fresh/mac-1", port: 8771, claude: false).launch(["serve"], environment: mac)
    check(without.environment["FRIDAY_CLAUDE"] == "none", "without Claude: none")
    let initial = user.launch(["init", "--timezone", "America/New_York"], environment: mac)
    check(initial.arguments == ["--data-dir", "/tmp/fresh/mac-1/data", "init", "--timezone", "America/New_York"],
          "init takes no port: \(initial.arguments)")
}

test("Server.prepare: yours as before, a test user's in its folder") {
    let installed = Server.Launcher(executable: URL(fileURLWithPath: "/Users/someone/.local/bin/fridayd"))
    let yours = Process()
    Server.prepare(yours, installed, ["serve"], user: nil)
    check(yours.arguments == ["serve"] && yours.environment == nil, "yours inherits the app's environment")
    let theirs = Process()
    Server.prepare(theirs, installed, ["serve"], user: TestUser(folder: "/tmp/f", port: 8770, claude: true))
    check(theirs.arguments == ["--data-dir", "/tmp/f/data", "serve", "--port", "8770"], "\(theirs.arguments ?? [])")
    check(theirs.environment?["FRIDAY_CALENDARS_READ_ONLY"] == "1", "its environment")
}

test("a new test user: a folder of its own, kept, a port nothing uses") {
    let root = scratch(), defaults = UserDefaults(suiteName: "friday-test-\(UUID().uuidString)")!
    var parts = DateComponents()
    (parts.year, parts.month, parts.day, parts.hour, parts.minute, parts.second) = (2026, 10, 29, 0, 30, 12)
    let now = Calendar.current.date(from: parts)!
    check(TestUser.kept(defaults: defaults) == nil, "none kept at first")
    let first = TestUser.make(claude: true, root: root, now: now, defaults: defaults, isFree: { $0 != 8770 })
    check(first.name == "mac-2026-10-29-003012", "named for when: \(first.name)")
    check(first.port == 8771, "8770 is busy: \(first.port)")
    var isDir: ObjCBool = false
    check(FileManager.default.fileExists(atPath: first.folder + "/config", isDirectory: &isDir) && isDir.boolValue,
          "its config folder made")
    check(TestUser.kept(defaults: defaults) == first, "kept for the next start")
    let again = TestUser.make(claude: false, root: root, now: now, defaults: defaults, isFree: { _ in true })
    check(again.name == "mac-2026-10-29-003012-2", "the same second: another folder, \(again.name)")
    check(TestUser.kept(defaults: defaults) == again && !again.claude, "the newest is the one kept")
    check(FileManager.default.fileExists(atPath: first.folder), "the old user's folder stays")
    try? FileManager.default.removeItem(at: root)
}

test("a port: the first free from where it starts, never yours") {
    check(TestUser.freePort(from: 8770, isFree: { _ in true }) == 8770, "the first")
    check(TestUser.freePort(from: 8764, isFree: { $0 != 8764 }) == 8766, "skips the busy one and 8765")
    check(TestUser.freePort(from: 8770, isFree: { $0 > 8775 }) == 8776, "past several")
    let s = socket(AF_INET, SOCK_STREAM, 0)
    var address = sockaddr_in()
    address.sin_family = sa_family_t(AF_INET)
    address.sin_addr.s_addr = inet_addr("127.0.0.1")
    address.sin_port = 0
    var length = socklen_t(MemoryLayout<sockaddr_in>.size)
    _ = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(s, $0, length) } }
    listen(s, 1)
    _ = withUnsafeMutablePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(s, $0, &length) } }
    let taken = Int(UInt16(bigEndian: address.sin_port))
    check(!TestUser.isFree(taken), "a port something listens on is busy (\(taken))")
    close(s)
    check(TestUser.isFree(taken), "free again once closed (\(taken))")
}

test("Friday Test refuses every change to the Mac's calendars, saying why") {
    let refused = TestCalendars.refuse(["id": 7, "op": "create", "calendar": "Home"])
    check(refused["id"] as? Int == 7 && refused["ok"] as? Bool == false, "\(refused)")
    check(refused["error"] as? String == "Friday Test never changes this Mac's calendars", "said")
    check(TestCalendars.refuse(["op": "delete"]).isEmpty, "a job without an id: nothing to answer")
}

test("Friday Test opens as a new user each time, unless kept and not started over") {
    check(TestUser.startsNew(keep: false, asked: false), "not kept: new")
    check(!TestUser.startsNew(keep: true, asked: false), "kept: the same user")
    check(TestUser.startsNew(keep: true, asked: true), "Start Over beats keeping")
    let root = scratch(), defaults = UserDefaults(suiteName: "friday-test-\(UUID().uuidString)")!
    let first = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    let second = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    check(first != second && TestUser.kept(defaults: defaults) == second, "two openings, two users")
    defaults.set(true, forKey: TestUser.keepKey)
    check(TestUser.opening(defaults: defaults, root: root, isFree: { _ in true }) == second, "kept: opens as the last one")
    defaults.set(true, forKey: TestUser.askedKey)
    defaults.set(false, forKey: TestUser.claudeKey)
    let over = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    check(over != second && !over.claude, "Start Over without Claude: a new user without it")
    check(!defaults.bool(forKey: TestUser.askedKey), "asked once: the next opening keeps it again")
    check(TestUser.opening(defaults: defaults, root: root, isFree: { _ in true }) == over, "kept from then on")
    try? FileManager.default.removeItem(at: root)
}

test("only the newest test users' folders stay; nothing else there is touched") {
    let root = scratch()
    let names = (1 ... 11).map { String(format: "mac-2026-10-%02d-120000", $0) } + ["mac-2026-10-05-120000-2", "2026-10-28-225128", "current"]
    for n in names { try? FileManager.default.createDirectory(at: root.appendingPathComponent(n), withIntermediateDirectories: true) }
    let stale = TestUser.stale(in: root, keeping: 8).map(\.lastPathComponent)
    check(stale == ["mac-2026-10-01-120000", "mac-2026-10-02-120000", "mac-2026-10-03-120000", "mac-2026-10-04-120000"],
          "the four oldest of twelve: \(stale)")
    check(!stale.contains("2026-10-28-225128") && !stale.contains("current"), "fresh_user.sh's are never Friday Test's")
    let defaults = UserDefaults(suiteName: "friday-test-\(UUID().uuidString)")!
    _ = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    let left = ((try? FileManager.default.contentsOfDirectory(atPath: root.path)) ?? []).filter { $0.hasPrefix("mac-") }
    check(left.count == TestUser.keeping, "a new user, and the newest \(TestUser.keeping) kept: \(left.count)")
    check(FileManager.default.fileExists(atPath: root.appendingPathComponent("2026-10-28-225128").path), "the website's test user stays")
    try? FileManager.default.removeItem(at: root)
}

test("a repeat Friday asks of a Mac event, as EventKit's rule") {
    // 30 Oct: "the friday night salsa that's on this week should be a weekly event"
    let weekly = MacWriter.recurrence("FREQ=WEEKLY;BYDAY=FR")!
    check(weekly.frequency == .weekly && weekly.interval == 1, "every week")
    check(weekly.daysOfTheWeek?.map(\.dayOfTheWeek) == [.friday], "on Fridays")
    check(weekly.recurrenceEnd == nil, "for good")
    let fortnight = MacWriter.recurrence("FREQ=WEEKLY;INTERVAL=2;BYDAY=TH")!
    check(fortnight.interval == 2 && fortnight.daysOfTheWeek?.map(\.dayOfTheWeek) == [.thursday], "every other Thursday")
    let york = TimeZone(identifier: "America/New_York")!
    let until = MacWriter.recurrence("FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261211T235959", zone: york)!
    check(until.daysOfTheWeek?.count == 2, "two days")
    check(until.recurrenceEnd?.endDate == Date(timeIntervalSince1970: 1_797_051_599), "until the 11th, in this Mac's time")
    check(MacWriter.recurrence("FREQ=DAILY;COUNT=5")?.recurrenceEnd?.occurrenceCount == 5, "five times")
    check(MacWriter.recurrence("FREQ=HOURLY") == nil && MacWriter.recurrence("nonsense") == nil, "what it can't read")
}

test("a build with a feed tells its server the feed; every bundled one its version and place (H169)") {
    let home = URL(fileURLWithPath: "/Users/someone")
    let python = URL(fileURLWithPath: "/Applications/Friday.app/Contents/Resources/friday/python/bin/python3.12")
    let downloaded = Server.ThisApp(version: "0.2.0", path: "/Applications/Friday.app",
                                    feed: "https://site.example/updates.json")
    let env = Server.bundledLauncher(python, home: home, exists: { _ in false }, app: downloaded).environment([:])
    check(env["FRIDAY_APP_VERSION"] == "0.2.0" && env["FRIDAY_APP_PATH"] == "/Applications/Friday.app", "its version, its place")
    check(env["FRIDAY_UPDATE_FEED"] == "https://site.example/updates.json", "the feed it looks at")
    let yours = Server.ThisApp(version: "0.2.0", path: "/Applications/Friday.app", feed: nil)
    let built = Server.bundledLauncher(python, home: home, exists: { _ in false }, app: yours).environment([:])
    check(built["FRIDAY_UPDATE_FEED"] == nil && built["FRIDAY_APP_VERSION"] == "0.2.0", "a build without a feed (Friday Test) never looks")
}

test("the updater swaps in only a Friday.app the server unpacked into its updates folder") {
    let cache = URL(fileURLWithPath: "/Users/someone/Library/Caches/Friday/updates")
    check(Updater.accepted("/Users/someone/Library/Caches/Friday/updates/0.2.0/Friday.app", cache: cache) != nil, "its own")
    check(Updater.accepted("/Users/someone/Downloads/Friday.app", cache: cache) == nil, "anywhere else")
    check(Updater.accepted("/Users/someone/Library/Caches/Friday/updates/../../../Evil/Friday.app", cache: cache) == nil,
          "not by climbing out")
    check(Updater.accepted("/Users/someone/Library/Caches/Friday/updates/0.2.0/Other.app", cache: cache) == nil,
          "only Friday.app")
}

test("the swap waits for Friday to quit, puts the new app in place, and the old back if it can't") {
    let files = FileManager.default
    let root = files.temporaryDirectory.appendingPathComponent("friday-swap-\(UUID().uuidString)")
    let app = root.appendingPathComponent("Applications/Friday.app")
    let staged = root.appendingPathComponent("updates/0.2.0/Friday.app")
    try? files.createDirectory(at: app, withIntermediateDirectories: true)
    try? files.createDirectory(at: staged, withIntermediateDirectories: true)
    try? "0.1.0".write(to: app.appendingPathComponent("version"), atomically: true, encoding: .utf8)
    try? "0.2.0".write(to: staged.appendingPathComponent("version"), atomically: true, encoding: .utf8)
    func swap(waitingFor pid: Int32) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = Updater.swapArguments(pid: pid, app: app, staged: staged, reopen: false)
        try? process.run()
        process.waitUntilExit()
    }
    let gone = Process()
    gone.executableURL = URL(fileURLWithPath: "/usr/bin/true")
    try? gone.run()
    gone.waitUntilExit()  // a Friday that has quit
    swap(waitingFor: gone.processIdentifier)
    let now = try? String(contentsOf: app.appendingPathComponent("version"), encoding: .utf8)
    check(now == "0.2.0", "the new version in place: \(now ?? "nothing")")
    check(!files.fileExists(atPath: staged.path), "moved, not copied")
    let left = (try? files.contentsOfDirectory(atPath: app.deletingLastPathComponent().path)) ?? []
    check(left == ["Friday.app"], "the old one gone: \(left)")
    swap(waitingFor: gone.processIdentifier)  // nothing staged any more: the swap can't happen
    let kept = try? String(contentsOf: app.appendingPathComponent("version"), encoding: .utf8)
    check(kept == "0.2.0", "the app put back when the new one can't be moved in: \(kept ?? "nothing")")
    try? files.removeItem(at: root)
}

test("an update keeps Friday Test's user through the restart, once; then it starts new again as set") {
    let defaults = UserDefaults(suiteName: "friday-test-updated-\(UUID().uuidString)")!
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("friday-fresh-\(UUID().uuidString)")
    let first = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    defaults.set(true, forKey: TestUser.updatedKey)
    let after = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    check(after.folder == first.folder, "the same user after updating")
    check(defaults.object(forKey: TestUser.updatedKey) == nil, "only for that one opening")
    let next = TestUser.opening(defaults: defaults, root: root, isFree: { _ in true })
    check(next.folder != first.folder, "then a new user again, Keep This User being off")
    try? FileManager.default.removeItem(at: root)
}

test("the server stopping while it starts is said with what to do, the detail after (8 Nov)") {
    let busy = Server.startupWords(started: true, log: "ERROR: [Errno 48] error while attempting to bind: address already in use")
    check(busy.hasPrefix("Another app is using Friday's port"), "a taken port: quit the other copy")
    check(busy.contains("What it said:\n") && busy.contains("[Errno 48]"), "the detail stays, below")
    check(Server.startupWords(started: true, log: "sqlite3.OperationalError: database is locked").hasPrefix("Friday's data is in use"), "a locked database")
    check(Server.startupWords(started: true, log: "OSError: [Errno 28] No space left on device").hasPrefix("Your Mac's disk is full"), "a full disk")
    check(Server.startupWords(started: false, log: "The file doesn't exist.").hasPrefix("Friday's server couldn't be opened"), "not opened at all")
    let other = Server.startupWords(started: true, log: "Traceback (most recent call last): …")
    check(other.contains("friday_support@friday-scheduler.com") && !other.hasPrefix("Traceback"), "anything else: plain words first")
    check(Server.startupWords(started: true, log: "  ").hasSuffix("with what happened."), "no detail: no heading, nothing pointed at")
}

test("a reminder reaches Friday with its list and its due as Friday reads it (C100)") {
    check(RemindersPayload.due(DateComponents(year: 2026, month: 11, day: 20)) == "2026-11-20", "a whole day")
    check(RemindersPayload.due(DateComponents(year: 2026, month: 11, day: 20, hour: 17, minute: 5)) == "2026-11-20T17:05",
          "at a time, to the minute")
    check(RemindersPayload.due(DateComponents(year: 2026, month: 11, day: 20, hour: 9)) == "2026-11-20T09:00", "on the hour")
    check(RemindersPayload.due(DateComponents(hour: 9)) == nil, "no day: no due")
    let r = EKReminder(eventStore: EKEventStore())
    r.title = "Pay rent"
    r.dueDateComponents = DateComponents(year: 2026, month: 11, day: 1, hour: 9, minute: 0)
    r.url = URL(string: "https://bank.example")
    let sent = RemindersPayload.reminder(r)
    check(sent["title"] as? String == "Pay rent" && sent["due"] as? String == "2026-11-01T09:00", "\(sent)")
    check(sent["url"] as? String == "https://bank.example" && sent["completed"] as? Bool == false, "\(sent)")
    check(!(sent["id"] as? String ?? "").isEmpty, "known by its own id")
}

test("done or opened again in Friday is made on the reminder, once, and a refusal said (C100)") {
    let r = EKReminder(eventStore: EKEventStore())
    var saved = 0
    let done = ReminderWriter.apply("done", to: r, id: 4) { _ in saved += 1 }
    check(r.isCompleted && saved == 1 && done["ok"] as? Bool == true && done["id"] as? Int == 4, "ticked off")
    _ = ReminderWriter.apply("done", to: r, id: 5) { _ in saved += 1 }
    check(saved == 1, "already done: not saved again")
    struct No: LocalizedError { var errorDescription: String? { "The list is read-only" } }
    let refused = ReminderWriter.apply("reopen", to: r, id: 6) { _ in throw No() }
    check(r.isCompleted && refused["ok"] as? Bool == false && refused["error"] as? String == "The list is read-only",
          "refused: left as it was, the reason said")
    check(ReminderWriter.apply("delete", to: r, id: 7) { _ in saved += 1 }["ok"] as? Bool == false && saved == 1,
          "only done and reopen")
    let test = ReminderWriter.refuse(["id": 8])
    check(test["ok"] as? Bool == false && test["error"] as? String == ReminderWriter.refusal, "Friday Test changes none of yours")
}

test("Things' to-dos read from its AppleScript answer: the open ones, their deadline and When day (C108)") {
    func list(_ items: [NSAppleEventDescriptor]) -> NSAppleEventDescriptor {
        let out = NSAppleEventDescriptor.list()
        for (i, d) in items.enumerated() { out.insert(d, at: i + 1) }
        return out
    }
    func status(_ code: String) -> NSAppleEventDescriptor { NSAppleEventDescriptor(enumCode: ThingsScript.code(code)) }
    let nov20 = Calendar.current.date(from: DateComponents(year: 2026, month: 11, day: 20, hour: 0))!
    let answer = list([
        list([NSAppleEventDescriptor(string: "A1"), NSAppleEventDescriptor(string: "B2")]),
        list([NSAppleEventDescriptor(string: "File taxes"), NSAppleEventDescriptor(string: "Done already")]),
        list([NSAppleEventDescriptor(string: "Forms in the drawer"), NSAppleEventDescriptor(string: "")]),
        list([NSAppleEventDescriptor(date: nov20), NSAppleEventDescriptor.null()]),
        list([NSAppleEventDescriptor.null(), NSAppleEventDescriptor(date: nov20)]),
        list([status("tdio"), status("tdcm")]),
    ])
    let todos = ThingsScript.todos(answer, list: "Today")
    check(todos.count == 1, "only the open one: \(todos)")
    check(todos.first?["id"] as? String == "A1" && todos.first?["due"] as? String == "2026-11-20", "\(todos)")
    check(todos.first?["when"] == nil && todos.first?["list"] as? String == "Today", "no When day: none sent")
    check(ThingsScript.todos(list([list([]), list([]), list([]), list([]), list([]), list([])]), list: "Inbox").isEmpty,
          "an empty list")
}

test("a Things to-do is ticked only by an id that can't break out of the script; Friday Test ticks none (C108)") {
    let sneaky = ThingsScript.apply(["id": 3, "external_id": "A1\" to open\ndo shell script \"rm", "op": "done"])
    check(sneaky["ok"] as? Bool == false, "an id with quotes isn't put in a script")
    check(ThingsScript.apply(["id": 4, "external_id": "A1", "op": "delete"])["ok"] as? Bool == false, "only done and reopen")
    check(ThingsScript.refuse(["id": 5])["error"] as? String == ThingsScript.refusal, "Friday Test changes none of yours")
}

test("the plan's calendar holds exactly the plan: made, moved, renamed, gone, a duplicate removed (C113)") {
    let t0 = Date(timeIntervalSince1970: 1_792_000_000)
    let at = { (m: Double) in t0.addingTimeInterval(m * 60) }
    let have = [
        PlanCalendar.Have(key: "1@a", title: "essay", start: at(0), end: at(90), id: "e1"),
        PlanCalendar.Have(key: "2@b", title: "lab", start: at(120), end: at(180), id: "e2"),
        PlanCalendar.Have(key: "3@c", title: "gone", start: at(200), end: at(260), id: "e3"),
        PlanCalendar.Have(key: "1@a", title: "essay", start: at(0), end: at(90), id: "e4"),
    ]
    let wanted = [
        PlanCalendar.Wanted(key: "1@a", title: "essay", start: at(0), end: at(90)),
        PlanCalendar.Wanted(key: "2@b", title: "lab report", start: at(150), end: at(210)),
        PlanCalendar.Wanted(key: "4@d", title: "reading", start: at(300), end: at(330)),
    ]
    let (make, change, remove) = PlanCalendar.changes(have: have, wanted: wanted)
    check(make.map(\.key) == ["4@d"], "made: \(make)")
    check(change.map { $0.0.id } == ["e2"], "changed: the lab, moved and renamed")
    check(Set(remove.map(\.id)) == ["e3", "e4"], "removed: the gone block and the duplicate: \(remove)")
    let none = PlanCalendar.changes(have: Array(have.prefix(1)), wanted: Array(wanted.prefix(1)))
    check(none.make.isEmpty && none.change.isEmpty && none.remove.isEmpty, "as it is: nothing touched")
    let read = PlanCalendar.wanted([["key": "1@a", "title": "essay", "start": "2026-10-19T14:00:00Z", "end": "2026-10-19T15:30:00Z"],
                                    ["key": "bad", "title": "x", "start": "2026-10-19T15:00:00Z", "end": "2026-10-19T14:00:00Z"]])
    check(read.count == 1 && read[0].end.timeIntervalSince(read[0].start) == 5400, "the server's blocks read; a backwards one left out")
}

test("Friday's links: add a to-do, open a page or a new box; anything else is ignored (C114)") {
    let link = { (s: String) in FridayLink.of(URL(string: s)!, scheme: "friday") }
    check(link("friday://add?text=essay%203h%20due%20fri") == .add("essay 3h due fri"), "a to-do, as the add box reads it")
    check(link("friday://add?text=%20%20") == nil && link("friday://add") == nil, "nothing to add: nothing")
    check(link("friday://open?page=Inbox") == .open(.go("/inbox")) && link("friday://open") == .open(.go("/")), "a page")
    check(link("friday://open?page=passwords") == nil, "a page Friday doesn't have")
    check(link("friday://new?what=event") == .open(.newEvent) && link("friday://new") == .open(.newTodo), "a new box")
    check(link("fridaytest://add?text=x") == nil, "Friday Test's links aren't Friday's")
    check(FridayLink.of(URL(string: "fridaytest://add?text=x")!, scheme: "fridaytest") == .add("x"), "and the other way")
    check(link("friday://delete?all=1") == nil, "anything else: ignored")
}

test("a + in a link's text is a +, %2B one too, and %20 or a space a space (the audit, 12 Nov)") {
    let link = { (s: String) in FridayLink.of(URL(string: s)!, scheme: "friday") }
    check(link("friday://add?text=C++%20homework") == .add("C++ homework"), "C++ stays C++, not \"C  \"")
    check(link("friday://add?text=+1%20call%20mom") == .add("+1 call mom"), "+1 keeps its +")
    check(link("friday://add?text=essay+3h") == .add("essay+3h"), "a + is never read as a space (a link isn't a form)")
    check(link("friday://add?text=a%2Bb%20c") == .add("a+b c"), "%2B is a +, %20 a space")
    check(link("friday://add?text=%2B%2B") == .add("++"), "only pluses")
    check(link("friday://add?text=+") == .add("+") && link("friday://add?text=%2B") == .add("+"), "a + alone is something to add")
    // Shortcuts' Open URLs hands over the text as typed; macOS encodes its spaces, never its pluses
    if let typed = URL(string: "friday://add?text=C++ 2h due fri") {
        check(FridayLink.of(typed, scheme: "friday") == .add("C++ 2h due fri"), "typed with spaces: \(typed.absoluteString)")
    }
}

test("a server left over from another build is stopped; this build's, a hand-started one or a live app's is used") {
    let theirs: [String: Any] = ["server_build": "old", "server_orphan": true, "server_pid": 4242]
    check(Server.leftover(theirs, mine: "new") == 4242, "another build's, its app gone: stopped")
    check(Server.leftover(theirs, mine: "old") == nil, "this build's own: used")
    check(Server.leftover(theirs.merging(["server_orphan": false]) { $1 }, mine: "new") == nil, "its app still open: used")
    check(Server.leftover(["server_orphan": true, "server_pid": 4242], mine: "new") == nil, "started by hand: used")
    check(Server.leftover(theirs, mine: nil) == nil, "a build without a stamp stops nothing")
    check(Server.leftover(theirs.merging(["server_pid": 1]) { $1 }, mine: "new") == nil, "never launchd")
}

test("Siri says what's on and what's next, in 12-hour times, the day named when it isn't today (C131)") {
    let today = "2026-11-11"
    let gym: [String: Any] = ["title": "Gym", "start": "2026-11-12T07:30", "end": "2026-11-12T09:00"]
    let essay: [String: Any] = ["title": "CS essay", "start": "2026-11-11T15:00", "end": "2026-11-11T16:45"]
    check(SiriSays.next(["current": essay, "current_source": "plan", "next": gym], today: today)
          == "Now: CS essay, until 4:45pm. Then Gym at 7:30am tomorrow.", "on now, then next")
    check(SiriSays.next(["current": NSNull(), "next": gym], today: today) == "You're free until 7:30am tomorrow. Then Gym.", "free")
    check(SiriSays.next(["current": essay, "current_source": "timer", "next": NSNull()], today: today)
          == "You're timing CS essay.", "timing, nothing after")
    check(SiriSays.next(["current": NSNull(), "next": NSNull()], today: today) == "Nothing else is planned.", "nothing")
    check(SiriSays.next(nil, today: today) == SiriSays.notRunning, "Friday not answering")
    check(SiriSays.time("2026-11-11T12:00") == "12pm" && SiriSays.time("2026-11-11T00:05") == "12:05am", "noon, midnight")
    check(SiriSays.day("2026-11-14T10:00", today: today) == " on Saturday", "this week: its day")
    check(SiriSays.day("2026-11-20T10:00", today: today) == " on 20 Nov", "later: its date")
    check(SiriSays.day("2026-11-11T10:00", today: today, always: true) == " today", "today, when asked")
}

test("Siri says what was added, or why it wasn't (C131)") {
    check(SiriSays.added(["message": "give it a title: what is it?"]) == "Friday couldn't add that: give it a title: what is it?", "refused")
    check(SiriSays.added(["result": ["item": ["title": "Read ch. 4", "when": "flexible"]]]) == "Added Read ch. 4. Friday plans it.", "a to-do")
    check(SiriSays.added(["result": ["series_id": 3, "occurrences": 8]]) == "Added, repeating: 8 planned so far.", "a repeat")
    check(SiriSays.added(nil) == SiriSays.notRunning, "not answering")
    let due = SiriSays.added(["result": ["item": ["title": "Essay", "when": "flexible", "due": "2099-01-02T17:00"]]])
    check(due == "Added Essay, due 5pm on 2 Jan.", "with its due: \(due)")
}

test("the server's output is read until it stops, then no more (audit, 12 Nov: the end was read for ever)") {
    final class Count: @unchecked Sendable {
        var calls = 0
        var text = ""
        let lock = NSLock()
    }
    let count = Count()
    let echo = Process()
    echo.executableURL = URL(fileURLWithPath: "/bin/echo")
    echo.arguments = ["Uvicorn running"]
    let pipe = Pipe()
    echo.standardOutput = pipe
    pipe.fileHandleForReading.readabilityHandler = Server.reader { text in
        count.lock.lock()
        count.calls += 1
        count.text += text
        count.lock.unlock()
    }
    try? echo.run()
    echo.waitUntilExit()
    Thread.sleep(forTimeInterval: 0.5)
    count.lock.lock()
    let (calls, text) = (count.calls, count.text)
    count.lock.unlock()
    check(text == "Uvicorn running\n", "what it said: \(text)")
    check(calls < 5, "read \(calls) times after it stopped")
    check(pipe.fileHandleForReading.readabilityHandler == nil, "stopped reading at the end")
}

test("a calendar or reminders body counts as unchanged only when it's the same, not just as long (audit, 12 Nov)") {
    let header = String(repeating: "x", count: 90)
    let ten = Data("\(header)10:00".utf8), eleven = Data("\(header)11:00".utf8)
    let now = Date()
    check(!MacPayload.unchanged(eleven, since: (ten, now), now: now), "an event moved an hour is a change")
    check(MacPayload.unchanged(ten, since: (ten, now.addingTimeInterval(-60)), now: now), "the same within the hour")
    check(!MacPayload.unchanged(ten, since: (ten, now.addingTimeInterval(-3700)), now: now), "sent again after an hour")
}

test("a swap that can't move the old app aside opens it again, rather than leaving Friday closed") {
    let files = FileManager.default
    let root = files.temporaryDirectory.appendingPathComponent("friday-stuck-\(UUID().uuidString)")
    let folder = root.appendingPathComponent("Applications")
    let app = folder.appendingPathComponent("Friday.app")
    let staged = root.appendingPathComponent("updates/0.2.0/Friday.app")
    let bin = root.appendingPathComponent("bin")
    try? files.createDirectory(at: app, withIntermediateDirectories: true)
    try? files.createDirectory(at: staged, withIntermediateDirectories: true)
    try? files.createDirectory(at: bin, withIntermediateDirectories: true)
    // `open` stood in for: it notes what it was asked to open
    let opened = root.appendingPathComponent("opened")
    let open = bin.appendingPathComponent("open")
    try? "#!/bin/sh\necho \"$1\" > '\(opened.path)'\n".write(to: open, atomically: true, encoding: .utf8)
    try? files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: open.path)
    try? files.setAttributes([.posixPermissions: 0o555], ofItemAtPath: folder.path)  // Friday.app can't be moved
    let gone = Process()
    gone.executableURL = URL(fileURLWithPath: "/usr/bin/true")
    try? gone.run()
    gone.waitUntilExit()
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/sh")
    process.arguments = Updater.swapArguments(pid: gone.processIdentifier, app: app, staged: staged, reopen: true)
    process.environment = ["PATH": "\(bin.path):/usr/bin:/bin"]
    try? process.run()
    process.waitUntilExit()
    let said = (try? String(contentsOf: opened, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines)
    check(process.terminationStatus == 1, "it says it failed")
    check(said == app.path, "the old Friday opened again: \(said ?? "nothing")")
    check(files.fileExists(atPath: staged.path), "the new one left where it was")
    try? files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: folder.path)
    try? files.removeItem(at: root)
}

test("a server that stops by itself is started again, but not a fourth time in five minutes (audit, 12 Nov)") {
    let now = Date()
    check(Server.restartAgain(after: [], now: now), "the first time")
    check(Server.restartAgain(after: [now.addingTimeInterval(-60), now.addingTimeInterval(-30)], now: now), "the third")
    let three = [now.addingTimeInterval(-200), now.addingTimeInterval(-60), now.addingTimeInterval(-30)]
    check(!Server.restartAgain(after: three, now: now), "not a fourth within five minutes")
    check(Server.restartAgain(after: three.map { $0.addingTimeInterval(-400) }, now: now), "long ago don't count")
}

print(failures == 0 ? "All passed" : "\(failures) failed")
exit(failures == 0 ? 0 : 1)
