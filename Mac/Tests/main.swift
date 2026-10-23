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
        (.pace, "pace"), (.brief, "brief"), (.triage, "triage"),
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
    check(found.contains("/Users/someone/Downloads/Code/Friday-planner/.venv/bin/fridayd"), "the checkout")
    check(Server.candidates(chosen: "", home: home).first == home.appendingPathComponent(".local/bin/fridayd"),
          "an empty choice is no choice")
    check(Server.candidates(chosen: nil, home: home).count == 4, "four usual places")
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

test("only notifications newer than the last shown, oldest first") {
    let found: [[String: Any]] = [["id": 9, "title": "c"], ["id": 7, "title": "b"], ["id": 5, "title": "a"]]
    check(Notifier.unseen(found, after: 6).compactMap { $0["id"] as? Int } == [7, 9], "after 6")
    check(Notifier.unseen(found, after: 9).isEmpty, "all seen")
    check(Notifier.unseen([], after: 0).isEmpty, "none")
    check(Notifier.unseen([["title": "no id"]], after: 0).isEmpty, "one without an id isn't new")
}

print(failures == 0 ? "All passed" : "\(failures) failed")
exit(failures == 0 ? 0 : 1)
