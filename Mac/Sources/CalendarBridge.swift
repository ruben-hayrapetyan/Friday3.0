import AppKit
import EventKit

/// The Mac's calendars, fed to Friday's server (COMBINED.md 4): what EventKit sees from yesterday to twelve weeks out,
/// posted to `mac_sync` at launch, whenever a calendar changes and every ten minutes. The server reads each calendar
/// you switch on in Settings → Calendars, as it reads Google's. The other way, every twenty seconds: what you changed
/// in Friday about those calendars' events (`mac_writes`), made here so a Google or iCloud calendar gets it from the
/// Mac's own sync, each answered (`mac_written`).
@MainActor
final class CalendarBridge {
    private let store = EKEventStore()
    private var poll: Timer?
    private var writes: Timer?
    private var writing = false
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
        writes = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { _ in
            _ = Task { @MainActor in await self.write() }
        }
        soon()
    }

    /// Friday's waiting changes, one at a time; each answer goes back before the next (and before the change's own
    /// EKEventStoreChanged sends the calendars again), so the server knows the event's new id when it reads them.
    private func write() async {
        guard !writing else { return }
        writing = true
        defer { writing = false }
        guard let jobs = await Server.get("api/q/mac_writes") as? [[String: Any]] else { return }
        for job in jobs {
            let answer = MacWriter.apply(job, in: store)
            if answer["id"] != nil { await Server.post("mac_written", answer) }
        }
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

/// A change Friday asks of one of the Mac's events (api/views.py MacWriteOut), made through EventKit: its times and, when
/// you renamed it or moved it somewhere else in Friday, its title and place; or a delete. Only that occurrence of a
/// repeating event changes. Or a new event Friday made, for one of the Mac's calendars (27 Oct: your Gmail calendar,
/// which Friday reads through the Mac, so the event reaches Google through the Mac's own sync).
enum MacWriter {
    /// Makes one change; the answer for `mac_written`, with the event as it now is.
    static func apply(_ job: [String: Any], in store: EKEventStore, made: Made = .shared) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        if job["op"] as? String == "create", let calendar = job["calendar"] as? String {
            return create(job, id: id, calendar: calendar, in: store, made: made)
        }
        guard let op = job["op"] as? String, let calendar = job["calendar"] as? String,
              let occurrence = job["event"] as? String else {
            return ["id": id, "ok": false, "error": "Friday's change didn't say which event"]
        }
        guard let event = find(occurrence, calendar: calendar, in: store) else {
            if op == "delete" { return ["id": id, "ok": true] }  // gone already
            return ["id": id, "ok": false, "error": "The event isn't on that calendar any more"]
        }
        do {
            if op == "delete" {
                try store.remove(event, span: .thisEvent, commit: true)
                return ["id": id, "ok": true]
            }
            if change(event, to: job) { try store.save(event, span: .thisEvent, commit: true) }
            var answer: [String: Any] = ["id": id, "ok": true]
            if let now = MacPayload.event(event) { answer["event"] = now }
            return answer
        } catch {
            store.reset()  // the half-made change isn't left on the store's copy
            return ["id": id, "ok": false, "error": error.localizedDescription]
        }
    }

    /// A new event on the calendar, as Friday has it. Made once: the job's id and the event are kept until Friday has
    /// the answer, so a job asked for again (the answer lost on its way) answers with the event made the first time.
    static func create(_ job: [String: Any], id: Int, calendar: String, in store: EKEventStore, made: Made) -> [String: Any] {
        if let before = made.event(for: id), let found = find(before.occurrence, calendar: before.calendar, in: store),
           let now = MacPayload.event(found) {
            return ["id": id, "ok": true, "event": now]
        }
        guard let place = store.calendar(withIdentifier: calendar) else {
            return ["id": id, "ok": false, "error": "That calendar isn't on this Mac any more"]
        }
        guard place.allowsContentModifications else {
            return ["id": id, "ok": false, "error": "\(place.title) can't be changed from this Mac"]
        }
        let event = EKEvent(eventStore: store)
        event.calendar = place
        event.title = job["title"] as? String ?? ""
        if let notes = job["notes"] as? String, !notes.isEmpty { event.notes = notes }
        _ = change(event, to: job)
        guard event.startDate != nil, event.endDate != nil else {
            return ["id": id, "ok": false, "error": "Friday's new event didn't say when"]
        }
        do {
            try store.save(event, span: .thisEvent, commit: true)
        } catch {
            store.reset()
            return ["id": id, "ok": false, "error": error.localizedDescription]
        }
        guard let now = MacPayload.event(event), let occurrence = now["id"] as? String else {
            return ["id": id, "ok": true]
        }
        made.keep(id, occurrence: occurrence, calendar: calendar)
        return ["id": id, "ok": true, "event": now]
    }

    /// The occurrence an id names (MacPayload.occurrenceID): its event, at its occurrence, on its calendar.
    static func find(_ occurrence: String, calendar: String, in store: EKEventStore) -> EKEvent? {
        guard let (identifier, at) = parts(occurrence), let place = store.calendar(withIdentifier: calendar) else { return nil }
        let fortnight: TimeInterval = 14 * 86400  // a repeat's occurrence moved away from its day is still found
        let near = store.predicateForEvents(withStart: at - fortnight, end: at + fortnight, calendars: [place])
        return store.events(matching: near).first { e in
            (e.eventIdentifier ?? e.calendarItemIdentifier) == identifier
                && Int((e.occurrenceDate ?? e.startDate).timeIntervalSince1970) == Int(at.timeIntervalSince1970)
        }
    }

    /// "<identifier>@<Unix seconds>" apart; the identifier may hold an @ of its own.
    static func parts(_ occurrence: String) -> (String, Date)? {
        guard let at = occurrence.lastIndex(of: "@"), let seconds = Int(occurrence[occurrence.index(after: at)...]) else {
            return nil
        }
        return (String(occurrence[..<at]), Date(timeIntervalSince1970: TimeInterval(seconds)))
    }

    /// Puts the job's times, and its title and place if it sends them, on the event; whether that changed anything.
    static func change(_ e: EKEvent, to job: [String: Any], calendar: Calendar = .current) -> Bool {
        var changed = false
        if let title = job["title"] as? String, e.title != title {
            e.title = title
            changed = true
        }
        if let location = job["location"] as? String, (e.location ?? "") != location {
            e.location = location.isEmpty ? nil : location  // "" takes the place off
            changed = true
        }
        let allDay = job["all_day"] as? Bool ?? false
        guard let start = moment(job["start"], allDay: allDay, calendar: calendar),
              let after = moment(job["end"], allDay: allDay, calendar: calendar) else { return changed }
        let end = allDay ? after.addingTimeInterval(-1) : after  // Friday ends whole days at the next one's start
        if e.isAllDay != allDay {
            e.isAllDay = allDay
            changed = true
        }
        if e.startDate == nil || abs(e.startDate.timeIntervalSince(start)) >= 60 {
            e.startDate = start
            changed = true
        }
        if e.endDate == nil || abs(e.endDate.timeIntervalSince(end)) >= 60 {
            e.endDate = end
            changed = true
        }
        return changed
    }

    /// "2026-10-25T19:30:00Z", or a whole day's "2026-10-25" (its start, on this Mac's calendar).
    static func moment(_ value: Any?, allDay: Bool, calendar: Calendar = .current) -> Date? {
        guard let text = value as? String else { return nil }
        if allDay {
            let parts = text.split(separator: "-").compactMap { Int($0) }
            guard parts.count == 3 else { return nil }
            return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
        }
        let format = ISO8601DateFormatter()
        format.formatOptions = [.withInternetDateTime]
        return format.date(from: text)
    }
}

/// The new events made for Friday, by the job that asked for each, until Friday has the answer: the Mac app asks for
/// waiting changes every twenty seconds, and one asked for again mustn't make its event twice.
final class Made: @unchecked Sendable {
    static let shared = Made(defaults: .standard)
    private let defaults: UserDefaults
    private let key = "fridayMadeEvents"

    init(defaults: UserDefaults) { self.defaults = defaults }

    func keep(_ job: Int, occurrence: String, calendar: String) {
        var kept = defaults.dictionary(forKey: key) as? [String: [String]] ?? [:]
        kept[String(job)] = [occurrence, calendar]
        defaults.set(kept, forKey: key)
    }

    func event(for job: Int) -> (occurrence: String, calendar: String)? {
        guard let pair = (defaults.dictionary(forKey: key) as? [String: [String]])?[String(job)], pair.count == 2 else {
            return nil
        }
        return (pair[0], pair[1])
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
        if let location = e.location?.trimmingCharacters(in: .whitespacesAndNewlines), !location.isEmpty {
            out["location"] = location
        }
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
