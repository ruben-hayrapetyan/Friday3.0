import Foundation

/// Friday's own links (C114: Shortcuts and Siri), opened by Shortcuts' "Open URLs" action, a link anywhere, or
/// `open friday://…` in a terminal; Siri runs any shortcut you name. Friday Test answers to fridaytest:// instead, so
/// the two never take each other's.
///
///     friday://add?text=essay 3h due fri     a to-do, read the way the add box reads it, without opening Friday
///     friday://open?page=inbox               a page: plan, todo, projects, inbox, insights, rules, settings
///     friday://new?what=event                the new-event (or to-do) box, Friday in front
enum FridayLink: Equatable {
    case add(String)
    case open(HostAction)

    static let pages = ["plan": "/", "todo": "/todo", "projects": "/projects", "inbox": "/inbox",
                        "insights": "/insights", "rules": "/rules", "settings": "/settings"]

    /// What a link asks; nil for one Friday doesn't know (it's ignored, nothing happens).
    static func of(_ url: URL, scheme: String) -> FridayLink? {
        guard url.scheme?.lowercased() == scheme, let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return nil }
        let asked = Dictionary((parts.queryItems ?? []).map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { a, _ in a })
        switch (url.host ?? "").lowercased() {
        case "add":
            let text = (asked["text"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty || text.count > 500 ? nil : .add(text)
        case "open":
            return pages[(asked["page"] ?? "plan").lowercased()].map { .open(.go($0)) }
        case "new":
            return (asked["what"] ?? "todo").lowercased() == "event" ? .open(.newEvent) : .open(.newTodo)
        default:
            return nil
        }
    }
}
