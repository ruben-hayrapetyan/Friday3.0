import Foundation

/// Friday's own links (C114: Shortcuts and Siri), opened by Shortcuts' "Open URLs" action, a link anywhere, or
/// `open friday://…` in a terminal; Siri runs any shortcut you name. Friday Test answers to fridaytest:// instead, so
/// the two never take each other's.
///
///     friday://add?text=essay 3h due fri     a to-do, read the way the add box reads it, without opening Friday;
///                                            everything after text= is the to-do, & and # included (13 Nov)
///     friday://open?page=inbox               a page: plan, todo, projects, inbox, insights, rules, settings
///     friday://new?what=event                the new-event (or to-do) box, Friday in front
enum FridayLink: Equatable {
    case add(String)
    case open(HostAction)

    static let pages = ["plan": "/", "todo": "/todo", "projects": "/projects", "inbox": "/inbox",
                        "insights": "/insights", "rules": "/rules", "settings": "/settings"]

    /// What a link asks; nil for one Friday doesn't know (it's ignored, nothing happens). Its query is read as a URL's,
    /// not a form's: a + stays a + ("C++", "+1"), %2B is one too, and only %20 (or a space) is a space.
    static func of(_ url: URL, scheme: String) -> FridayLink? {
        guard url.scheme?.lowercased() == scheme, let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return nil }
        let asked = Dictionary((parts.queryItems ?? []).map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { a, _ in a })
        switch (url.host ?? "").lowercased() {
        case "add":
            let text = (everythingAfterText(url) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty || text.count > 500 ? nil : .add(text)
        case "open":
            return pages[(asked["page"] ?? "plan").lowercased()].map { .open(.go($0)) }
        case "new":
            return (asked["what"] ?? "todo").lowercased() == "event" ? .open(.newEvent) : .open(.newTodo)
        default:
            return nil
        }
    }

    /// An add link's text: all of the link after its text=, decoded, with any & or # in it. Shortcuts' Open URLs puts
    /// the Provided Input there as it is, so "Tom & Jerry" or "ch. 4 #2" would otherwise end at the & or #. nil when the
    /// link has no text=.
    static func everythingAfterText(_ url: URL) -> String? {
        let whole = url.absoluteString
        guard let mark = whole.firstIndex(of: "?") else { return nil }
        let rest = whole[whole.index(after: mark)...]
        let start: Substring.Index
        if rest.hasPrefix("text=") {
            start = rest.index(rest.startIndex, offsetBy: 5)
        } else if let found = rest.range(of: "&text=") {
            start = found.upperBound
        } else {
            return nil
        }
        let raw = String(rest[start...])
        return raw.removingPercentEncoding ?? raw  // a stray % ("100% done") is read as it is
    }
}
