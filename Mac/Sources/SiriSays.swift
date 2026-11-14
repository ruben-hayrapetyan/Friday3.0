import Foundation

/// What Siri says for Friday's own commands (C131: FridayIntents.swift), from the server's answers: plain sentences
/// with times on your clock (Settings → Appearance → Clock: 12-hour unless you chose 24), the day named when it isn't
/// today. Kept apart from App Intents so the tests can read it.
enum SiriSays {
    /// Your clock, "12h" or "24h", from `/api/q/settings`; the 12-hour one when Friday can't say.
    static func clock(_ settings: Any?) -> String {
        (settings as? [String: Any])?["clock"] as? String == "24h" ? "24h" : "12h"
    }

    /// What's on now and what's next, from `/api/q/now` (current, current_source, next; local "YYYY-MM-DDTHH:MM").
    static func next(_ now: [String: Any]?, today: String, clock: String = "12h") -> String {
        let time = { (local: String) in Self.time(local, clock: clock) }
        guard let now else { return notRunning }
        let current = now["current"] as? [String: Any]
        let coming = now["next"] as? [String: Any]
        var said: [String] = []
        if let current, let title = current["title"] as? String {
            if now["current_source"] as? String == "timer" {
                said.append("You're timing \(title).")
            } else if let end = current["end"] as? String {
                said.append("Now: \(title), until \(time(end))\(day(end, today: today)).")
            } else {
                said.append("Now: \(title).")
            }
        }
        if let coming, let title = coming["title"] as? String, let start = coming["start"] as? String {
            let at = "\(time(start))\(day(start, today: today))"
            said.append(current == nil ? "You're free until \(at). Then \(title)." : "Then \(title) at \(at).")
        } else if current == nil {
            said.append("Nothing else is planned.")
        }
        return said.joined(separator: " ")
    }

    /// What was added, from `/api/c/add`'s answer, or why it wasn't.
    static func added(_ answer: Any?, clock: String = "12h") -> String {
        let time = { (local: String) in Self.time(local, clock: clock) }
        guard let answer = answer as? [String: Any] else { return notRunning }
        if let refused = answer["message"] as? String, answer["result"] == nil { return "Friday couldn't add that: \(refused)" }
        let result = answer["result"] as? [String: Any] ?? [:]
        if result["series_id"] is Int, let made = result["occurrences"] as? Int {
            return "Added, repeating: \(made) planned so far."
        }
        guard let item = result["item"] as? [String: Any], let title = item["title"] as? String else { return "Added." }
        let today = Self.today()
        if item["when"] as? String == "fixed", let start = item["start"] as? String {
            return "Added \(title), \(time(start))\(day(start, today: today, always: true))."
        }
        if let due = item["due"] as? String {
            return "Added \(title), due \(time(due))\(day(due, today: today, always: true))."
        }
        return "Added \(title). Friday plans it."
    }

    static let notRunning = "Friday isn't answering yet. Open Friday, then ask again."

    /// "7:30am", "3pm", "12pm" from "YYYY-MM-DDTHH:MM"; "07:30", "15:00", "00:00" on the 24-hour clock.
    static func time(_ local: String, clock: String = "12h") -> String {
        let shown = local.split(separator: "T").last.map(String.init) ?? local
        let parts = shown.split(separator: ":").compactMap { Int($0) }
        guard parts.count >= 2 else { return shown }
        let (h, m) = (parts[0], parts[1])
        if clock == "24h" { return String(format: "%02d:%02d", h % 24, m) }
        let hour = h % 12 == 0 ? 12 : h % 12
        return "\(hour)\(m == 0 ? "" : String(format: ":%02d", m))\(h < 12 ? "am" : "pm")"
    }

    /// "" today, " tomorrow", " on Thursday" within the week, else " on 20 Nov"; " today" when `always`.
    static func day(_ local: String, today: String, always: Bool = false) -> String {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.dateFormat = "yyyy-MM-dd"
        guard let date = format.date(from: String(local.prefix(10))), let now = format.date(from: today) else { return "" }
        let days = Calendar(identifier: .gregorian).dateComponents([.day], from: now, to: date).day ?? 0
        if days == 0 { return always ? " today" : "" }
        if days == 1 { return " tomorrow" }
        format.dateFormat = days > 1 && days < 7 ? "EEEE" : "d MMM"
        return " on \(format.string(from: date))"
    }

    static func today() -> String {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.dateFormat = "yyyy-MM-dd"
        return format.string(from: Date())
    }

    /// The server's answer, tried for a while when Friday is still starting (Siri may have just opened it).
    static func ask(_ call: () async -> Any?) async -> Any? {
        for _ in 0 ..< 15 {
            if let answer = await call() { return answer }
            try? await Task.sleep(for: .seconds(1))
        }
        return nil
    }
}
