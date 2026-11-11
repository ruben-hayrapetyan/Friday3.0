import EventKit
import Foundation

/// Your plan as a "Friday" calendar on this Mac, in iCloud when you have it, so your iPhone shows it (C113; the
/// server's side is commands/mac_plan.py). Each of the plan's blocks is an event that knows its block by its URL
/// ("friday-block:<key>"), so a block moved is its event moved, one gone is its event gone, and nothing else in the
/// calendar is touched. Friday made the calendar, so switched off it removes it; and it's left out of what the Mac
/// app sends Friday (`mac_sync`), so the plan never comes back as busy time.
enum PlanCalendar {
    static let defaultsKey = "fridayPlanCalendar"
    static let scheme = "friday-block:"

    /// The calendar Friday made, while it's still there.
    static var identifier: String? { UserDefaults.standard.string(forKey: defaultsKey) }

    static func existing(in store: EKEventStore) -> EKCalendar? {
        identifier.flatMap { store.calendar(withIdentifier: $0) }
    }

    /// iCloud's account when this Mac has one (so the iPhone sees it), else where new calendars go, else on this Mac.
    static func source(in store: EKEventStore) -> EKSource? {
        store.sources.first { $0.sourceType == .calDAV && $0.title.lowercased().contains("icloud") }
            ?? store.defaultCalendarForNewEvents?.source
            ?? store.sources.first { $0.sourceType == .local }
    }

    static func calendar(in store: EKEventStore, name: String) throws -> EKCalendar? {
        if let found = existing(in: store) { return found }
        guard let place = source(in: store) else { return nil }
        let made = EKCalendar(for: .event, eventStore: store)
        made.title = name
        made.source = place
        made.cgColor = CGColor(red: 0.36, green: 0.55, blue: 0.94, alpha: 1)
        try store.saveCalendar(made, commit: true)
        UserDefaults.standard.set(made.calendarIdentifier, forKey: defaultsKey)
        return made
    }

    static func remove(in store: EKEventStore) {
        if let found = existing(in: store) { try? store.removeCalendar(found, commit: true) }
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    struct Wanted: Equatable {
        let key: String
        let title: String
        let start: Date
        let end: Date
    }

    struct Have: Equatable {
        let key: String
        let title: String
        let start: Date
        let end: Date
        let id: String
    }

    /// What to make, change and remove so the calendar holds exactly the wanted blocks.
    static func changes(have: [Have], wanted: [Wanted]) -> (make: [Wanted], change: [(Have, Wanted)], remove: [Have]) {
        let byKey = Dictionary(have.map { ($0.key, $0) }, uniquingKeysWith: { first, _ in first })
        let wantedKeys = Set(wanted.map(\.key))
        var make: [Wanted] = []
        var change: [(Have, Wanted)] = []
        for w in wanted {
            guard let h = byKey[w.key] else { make.append(w); continue }
            if h.title != w.title || abs(h.start.timeIntervalSince(w.start)) >= 60 || abs(h.end.timeIntervalSince(w.end)) >= 60 {
                change.append((h, w))
            }
        }
        let keep = Set(byKey.values.map(\.id))
        let remove = have.filter { !wantedKeys.contains($0.key) || !keep.contains($0.id) }  // a duplicate goes too
        return (make, change, remove)
    }

    /// The server's blocks ({key, title, start, end} in RFC 3339) as wanted events.
    static func wanted(_ blocks: [[String: Any]]) -> [Wanted] {
        let format = ISO8601DateFormatter()
        format.formatOptions = [.withInternetDateTime]
        return blocks.compactMap { b in
            guard let key = b["key"] as? String, let title = b["title"] as? String,
                  let start = (b["start"] as? String).flatMap(format.date), let end = (b["end"] as? String).flatMap(format.date),
                  end > start else { return nil }
            return Wanted(key: key, title: title, start: start, end: end)
        }
    }

    /// Makes the calendar hold the plan; whether it did.
    static func sync(_ blocks: [[String: Any]], name: String, in store: EKEventStore) -> Bool {
        do {
            guard let calendar = try calendar(in: store, name: name) else { return false }
            let from = Date().addingTimeInterval(-86400), to = Date().addingTimeInterval(120 * 86400)
            let events = store.events(matching: store.predicateForEvents(withStart: from, end: to, calendars: [calendar]))
            let have = events.compactMap { e -> Have? in
                guard let url = e.url?.absoluteString, url.hasPrefix(scheme), let id = e.eventIdentifier else { return nil }
                return Have(key: String(url.dropFirst(scheme.count)), title: e.title ?? "", start: e.startDate, end: e.endDate, id: id)
            }
            let (make, change, remove) = changes(have: have, wanted: wanted(blocks))
            for h in remove {
                if let e = store.event(withIdentifier: h.id) { try store.remove(e, span: .thisEvent, commit: false) }
            }
            for (h, w) in change {
                guard let e = store.event(withIdentifier: h.id) else { continue }
                e.title = w.title
                e.startDate = w.start
                e.endDate = w.end
                try store.save(e, span: .thisEvent, commit: false)
            }
            for w in make {
                let e = EKEvent(eventStore: store)
                e.calendar = calendar
                e.title = w.title
                e.startDate = w.start
                e.endDate = w.end
                e.url = URL(string: scheme + w.key)
                e.availability = .free  // your plan isn't someone else's meeting
                try store.save(e, span: .thisEvent, commit: false)
            }
            try store.commit()
            return true
        } catch {
            store.reset()
            return false
        }
    }
}
