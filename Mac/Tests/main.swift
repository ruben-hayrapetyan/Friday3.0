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

test("the server is on this Mac only") {
    check(Server.base.absoluteString == "http://127.0.0.1:8765/", "base \(Server.base)")
    check(URL(string: "api/q/item?id=3", relativeTo: Server.base)?.absoluteString == "http://127.0.0.1:8765/api/q/item?id=3",
          "a query survives")
}

test("Friday Test's server: the address chosen in defaults, else the one built in, with its slash") {
    let built = "https://laptop.tailnet.ts.net:8443"
    check(Server.hostedAddress(plist: built, chosen: nil)?.absoluteString == built + "/", "the built-in address")
    check(Server.hostedAddress(plist: built, chosen: "https://other.ts.net/")?.absoluteString == "https://other.ts.net/",
          "the one chosen wins")
    check(Server.hostedAddress(plist: built, chosen: "  ")?.absoluteString == built + "/", "a blank choice is no choice")
}

test("Friday Test's server: none for your Friday, for \"local\", or for an address that isn't one") {
    check(Server.hostedAddress(plist: nil, chosen: nil) == nil, "your Friday has none")
    check(Server.hostedAddress(plist: "https://x.ts.net:8443/", chosen: "local") == nil, "local: its own user again")
    check(Server.hostedAddress(plist: "not an address", chosen: nil) == nil, "no scheme or host")
    check(Server.hostedAddress(plist: "ftp://x.ts.net/", chosen: nil) == nil, "only the web")
}

test("a link stays in the window only on Friday's own server: same host and port, 443 when unsaid") {
    let staging = URL(string: "https://laptop.tailnet.ts.net:8443/")!
    let real = URL(string: "https://laptop.tailnet.ts.net/")!
    check(Server.isOwn(URL(string: "https://laptop.tailnet.ts.net:8443/todo")!, base: staging), "its own page")
    check(!Server.isOwn(URL(string: "https://laptop.tailnet.ts.net/")!, base: staging), "the other copy")
    check(Server.isOwn(URL(string: "https://laptop.tailnet.ts.net:443/x")!, base: real), "443 said or not")
    check(!Server.isOwn(URL(string: "https://calendar.google.com/")!, base: staging), "anywhere else: the browser")
    check(Server.isOwn(URL(string: "http://127.0.0.1:8765/x")!, base: URL(string: "http://127.0.0.1:8765/")!),
          "your local Friday as before")
}

test("Friday Test makes a local user only when it isn't opening the server's Friday") {
    let remote = URL(string: "https://laptop.tailnet.ts.net:8443/")!
    check(TestUser.makesLocalUser(isTest: true, remote: nil), "Friday Test, local")
    check(!TestUser.makesLocalUser(isTest: true, remote: remote), "Friday Test on the server: no folder made")
    check(!TestUser.makesLocalUser(isTest: false, remote: nil), "your Friday never")
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
    let yours = Process()
    Server.prepare(yours, ["serve"], user: nil)
    check(yours.arguments == ["serve"] && yours.environment == nil, "yours inherits the app's environment")
    let theirs = Process()
    Server.prepare(theirs, ["serve"], user: TestUser(folder: "/tmp/f", port: 8770, claude: true))
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

print(failures == 0 ? "All passed" : "\(failures) failed")
exit(failures == 0 ? 0 : 1)
