import AppKit
import EventKit

/// Apple Reminders, both ways (C100; the server's side is integrations/reminders.py). Every twenty seconds the Mac app
/// asks Friday whether Reminders is connected (`reminder_writes`). Only once it is does it ask macOS for your reminders,
/// so no one who never connects it is asked. Then it sends your open reminders (`reminders_sync`) when you connect it,
/// whenever Reminders changes and every ten minutes; and makes what you marked done or opened again in Friday, each
/// answered (`reminder_written`). macOS saying no is sent too, so the box in Settings says where to allow it.
@MainActor
final class RemindersBridge {
    private let store = EKEventStore()
    private var poll: Timer?
    private var busy = false
    private var watching = false
    private var asked = false  // macOS asked this launch: it answers once, from Settings after that
    private var pending: Task<Void, Never>?
    private var lastSent: (body: Int, at: Date)?
    private var lastDenied: Date?

    func start() {
        poll = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { _ in
            _ = Task { @MainActor in await self.tick() }
        }
        Task { await tick() }
    }

    private func tick() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        guard let said = await Server.get("api/q/reminder_writes") as? [String: Any] else { return }
        guard said["wanted"] as? Bool == true else {
            lastSent = nil  // connected again later: sent afresh at once
            return
        }
        guard await allowed() else {
            // said on the box, again every ten minutes in case the box was cleared
            if lastDenied.map({ Date().timeIntervalSince($0) > 600 }) ?? true,
               await Server.post("reminders_sync", ["denied": true]) != nil {
                lastDenied = Date()
            }
            return
        }
        lastDenied = nil
        if !watching { watch() }
        if lastSent == nil { await send() }
        for job in said["jobs"] as? [[String: Any]] ?? [] {
            let answer = TestUser.isTest ? ReminderWriter.refuse(job) : ReminderWriter.apply(job, in: store)
            if answer["id"] != nil { await Server.post("reminder_written", answer) }
        }
    }

    private func allowed() async -> Bool {
        if EKEventStore.authorizationStatus(for: .reminder) == .fullAccess { return true }
        // macOS asks only once; after a no (or a switch turned off) only System Settings can allow it, which the box
        // in Settings links to
        guard EKEventStore.authorizationStatus(for: .reminder) == .notDetermined, !asked else { return false }
        asked = true
        NSApp.activate()  // its question comes up in front, not behind another app's window
        return await withCheckedContinuation { done in
            store.requestFullAccessToReminders { granted, _ in done.resume(returning: granted) }
        }
    }

    private func watch() {
        watching = true
        NotificationCenter.default.addObserver(forName: .EKEventStoreChanged, object: store, queue: .main) { _ in
            MainActor.assumeIsolated { self.soon() }
        }
        Timer.scheduledTimer(withTimeInterval: 10 * 60, repeats: true) { _ in
            MainActor.assumeIsolated { self.soon() }
        }
    }

    /// A burst of changes (iCloud syncing your lists) sends once, two seconds after the last.
    private func soon() {
        pending?.cancel()
        pending = Task {
            try? await Task.sleep(for: .seconds(2))
            if !Task.isCancelled { await send() }
        }
    }

    private func send() async {
        let lists = store.calendars(for: .reminder)
        let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: lists)
        let open: [[String: Any]] = await withCheckedContinuation { done in
            store.fetchReminders(matching: predicate) { found in
                done.resume(returning: (found ?? []).map(RemindersPayload.reminder))
            }
        }
        let body: [String: Any] = ["reminders": open, "lists": lists.map(\.title)]
        let now = Date()
        // the same as last time, within the hour: nothing to say
        let digest = (try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]))?.hashValue ?? 0
        if let lastSent, lastSent.body == digest, now.timeIntervalSince(lastSent.at) < 3600 { return }
        if await Server.post("reminders_sync", body) != nil { lastSent = (digest, now) }
    }
}

/// What `reminders_sync` takes for one reminder (api/commands.py MacReminder).
enum RemindersPayload {
    static func reminder(_ r: EKReminder) -> [String: Any] {
        var out: [String: Any] = [
            "id": r.calendarItemIdentifier,
            "title": r.title ?? "",
            "notes": r.notes ?? "",
            "list": r.calendar?.title ?? "",
            "completed": r.isCompleted,
        ]
        if let due = r.dueDateComponents.flatMap(due) { out["due"] = due }
        if let url = r.url?.absoluteString { out["url"] = url }
        return out
    }

    /// A reminder's due as Friday reads it: "2026-11-20" for a whole day, "2026-11-20T17:00" at a time, this Mac's.
    static func due(_ parts: DateComponents) -> String? {
        guard let year = parts.year, let month = parts.month, let day = parts.day else { return nil }
        let date = String(format: "%04d-%02d-%02d", year, month, day)
        guard let hour = parts.hour else { return date }
        return date + String(format: "T%02d:%02d", hour, parts.minute ?? 0)
    }
}

/// A change Friday asks of one reminder (api/commands.py ReminderJob): ticked off, or opened again.
enum ReminderWriter {
    static let refusal = "Friday Test never changes this Mac's reminders"

    static func refuse(_ job: [String: Any]) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        return ["id": id, "ok": false, "error": refusal]
    }

    static func apply(_ job: [String: Any], in store: EKEventStore) -> [String: Any] {
        guard let id = job["id"] as? Int else { return [:] }
        guard let which = job["external_id"] as? String, let op = job["op"] as? String else {
            return ["id": id, "ok": false, "error": "Friday's change didn't say which reminder"]
        }
        guard let reminder = store.calendarItem(withIdentifier: which) as? EKReminder else {
            return ["id": id, "ok": true]  // deleted in Reminders since: nothing left to change
        }
        return apply(op, to: reminder, id: id) { try store.save($0, commit: true) }
    }

    /// The change itself, saved by `save`; the answer for `reminder_written`.
    static func apply(_ op: String, to reminder: EKReminder, id: Int, save: (EKReminder) throws -> Void) -> [String: Any] {
        let done = op == "done"
        guard done || op == "reopen" else { return ["id": id, "ok": false, "error": "Friday asked for \(op)"] }
        if reminder.isCompleted == done { return ["id": id, "ok": true] }  // already so
        reminder.isCompleted = done
        do {
            try save(reminder)
            return ["id": id, "ok": true]
        } catch {
            reminder.isCompleted = !done
            return ["id": id, "ok": false, "error": error.localizedDescription]
        }
    }
}
