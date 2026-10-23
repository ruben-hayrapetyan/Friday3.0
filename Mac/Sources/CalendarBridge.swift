import AppKit
import EventKit

/// The Mac's calendars, fed to Friday's server (COMBINED.md 4): what EventKit sees from yesterday to twelve weeks out,
/// posted to `mac_sync` at launch, whenever a calendar changes and every ten minutes. The server reads each calendar
/// you switch on in Settings → Calendars, as it reads Google's.
@MainActor
final class CalendarBridge {
    private let store = EKEventStore()
    private var poll: Timer?
    private var pending: Task<Void, Never>?
    private var lastSent: (body: Int, at: Date)?
    static let weeks = 12

    func start() {
        guard UserDefaults.standard.object(forKey: "macCalendars") as? Bool ?? true else { return }
        store.requestFullAccessToEvents { granted, _ in
            guard granted else { return }
            Task { @MainActor in self.watch() }
        }
    }

    private func watch() {
        NotificationCenter.default.addObserver(forName: .EKEventStoreChanged, object: store, queue: .main) { _ in
            MainActor.assumeIsolated { self.soon() }
        }
        poll = Timer.scheduledTimer(withTimeInterval: 10 * 60, repeats: true) { _ in
            MainActor.assumeIsolated { self.soon() }
        }
        soon()
    }

    /// A burst of changes (a calendar syncing) sends once, two seconds after the last.
    private func soon() {
        pending?.cancel()
        pending = Task {
            try? await Task.sleep(for: .seconds(2))
            if !Task.isCancelled { await send() }
        }
    }

    private func send() async {
        let now = Date()
        let since = Calendar.current.date(byAdding: .day, value: -1, to: Calendar.current.startOfDay(for: now))!
        let until = Calendar.current.date(byAdding: .day, value: 7 * Self.weeks, to: since)!
        let calendars = store.calendars(for: .event)
        let found = store.events(matching: store.predicateForEvents(withStart: since, end: until, calendars: calendars))
        let body = MacPayload.body(
            calendars: calendars.map(MacPayload.calendar),
            events: found.compactMap(MacPayload.event),
            since: since, until: until
        )
        // the same as last time, within the hour: nothing to say
        let digest = (try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]))?.hashValue ?? 0
        if let lastSent, lastSent.body == digest, now.timeIntervalSince(lastSent.at) < 3600 { return }
        if await Server.post("mac_sync", body) != nil { lastSent = (digest, now) }
    }
}

/// What `mac_sync` takes (api/commands.py MacSyncInput), from EventKit's objects.
enum MacPayload {
    static func body(calendars: [[String: Any]], events: [[String: Any]], since: Date, until: Date) -> [String: Any] {
        ["calendars": calendars, "events": events, "since": timestamp(since), "until": timestamp(until)]
    }

    static func calendar(_ c: EKCalendar) -> [String: Any] {
        var out: [String: Any] = [
            "id": c.calendarIdentifier,
            "name": c.title,
            "account": c.source?.title ?? "",
            "type": typeName(c.type),
            "writable": c.allowsContentModifications,
        ]
        if let color = c.color?.usingColorSpace(.sRGB) {
            out["color"] = hex(red: color.redComponent, green: color.greenComponent, blue: color.blueComponent)
        }
        return out
    }

    static func event(_ e: EKEvent) -> [String: Any]? {
        guard let calendar = e.calendar, let start = e.startDate, let end = e.endDate else { return nil }
        let identifier = e.eventIdentifier ?? e.calendarItemIdentifier
        var out: [String: Any] = [
            "id": occurrenceID(identifier, at: e.occurrenceDate ?? start),
            "calendar": calendar.calendarIdentifier,
            "title": e.title ?? "",
            "all_day": e.isAllDay,
            "free": e.availability == .free,
            "declined": e.attendees?.first(where: \.isCurrentUser)?.participantStatus == .declined,
        ]
        if e.isAllDay {
            out["start"] = day(start)
            out["end"] = day(allDayEnd(start: start, end: end))
        } else {
            out["start"] = timestamp(start)
            out["end"] = timestamp(end)
        }
        if e.hasRecurrenceRules { out["series"] = identifier }
        return out
    }

    /// Every occurrence of a repeating event shares EventKit's identifier; Friday needs one per occurrence.
    static func occurrenceID(_ identifier: String, at start: Date) -> String {
        "\(identifier)@\(Int(start.timeIntervalSince1970))"
    }

    /// EventKit ends an all-day event at the end of its last day; Google (and Friday) at the start of the next.
    static func allDayEnd(start: Date, end: Date, calendar: Calendar = .current) -> Date {
        let last = calendar.startOfDay(for: end == start ? end : end.addingTimeInterval(-1))
        return calendar.date(byAdding: .day, value: 1, to: last)!
    }

    static func day(_ date: Date, calendar: Calendar = .current) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
    }

    /// "2026-10-20T10:00:00-04:00": the Mac's own offset, so the server needn't know its zone.
    static func timestamp(_ date: Date, zone: TimeZone = .current) -> String {
        let format = ISO8601DateFormatter()
        format.timeZone = zone
        format.formatOptions = [.withInternetDateTime]
        let text = format.string(from: date)
        return text.hasSuffix("Z") ? String(text.dropLast()) + "+00:00" : text
    }

    static func typeName(_ type: EKCalendarType) -> String {
        switch type {
        case .local: return "local"
        case .calDAV: return "caldav"
        case .exchange: return "exchange"
        case .subscription: return "subscription"
        case .birthday: return "birthday"
        @unknown default: return "other"
        }
    }

    static func hex(red: CGFloat, green: CGFloat, blue: CGFloat) -> String {
        let byte = { (v: CGFloat) in Int((min(max(v, 0), 1) * 255).rounded()) }
        return String(format: "#%02x%02x%02x", byte(red), byte(green), byte(blue))
    }
}
