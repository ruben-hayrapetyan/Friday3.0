import Foundation

/// What the Mac app asks of the web app (COMBINED.md 5): a menu item, a global hotkey. Each is a `friday:host` event
/// the web app listens for (web/src/shell/useHost.ts), so the menus and the page share one implementation.
enum HostAction: Equatable {
    case newEvent
    case newTodo
    case search
    case askClaude
    case today, previous, next
    case view(String)  // "day" | "week" | "month"
    case drawer  // opens or closes it
    case openDrawer  // the summon hotkey: open, whatever it was
    case go(String)  // a page: "/", "/todo", "/projects", "/review", "/inbox", "/insights", "/rules", "/settings"
    case otherWays, shove, pace, brief, triage

    var name: String {
        switch self {
        case .newEvent: return "newEvent"
        case .newTodo: return "newTodo"
        case .search: return "search"
        case .askClaude: return "ask"
        case .today: return "today"
        case .previous: return "previous"
        case .next: return "next"
        case .view: return "view"
        case .drawer, .openDrawer: return "drawer"
        case .go: return "go"
        case .otherWays: return "ways"
        case .shove: return "shove"
        case .pace: return "pace"
        case .brief: return "brief"
        case .triage: return "triage"
        }
    }

    var argument: String? {
        switch self {
        case .view(let v): return v
        case .go(let path): return path
        case .openDrawer: return "open"
        default: return nil
        }
    }

    /// The JavaScript that sends this action to the page.
    var script: String {
        let detail: [String: String] = argument.map { ["action": name, "argument": $0] } ?? ["action": name]
        let json = (try? JSONSerialization.data(withJSONObject: detail, options: [.sortedKeys]))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        return "window.dispatchEvent(new CustomEvent('friday:host', { detail: \(json) }))"
    }
}
