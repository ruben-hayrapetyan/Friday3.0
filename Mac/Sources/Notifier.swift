import AppKit
import UserNotifications

/// Friday's notifications as the Mac's own (COMBINED.md 7): the server decides what to say and when (the morning
/// brief, a block starting, overload, "did you finish it?"); the Mac app shows each new one once.
@MainActor
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    private var poll: Timer?
    private let seenKey = "lastNotificationShown"

    func start() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        poll = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
            Task { @MainActor in await self.check() }
        }
        Task { await check() }
    }

    private func check() async {
        guard let found = await Server.get("api/q/notifications") as? [[String: Any]] else { return }
        let seen = UserDefaults.standard.integer(forKey: seenKey)
        let fresh = Notifier.unseen(found, after: seen)
        if seen == 0 {  // the first look only remembers where it is: no flood of old ones
            UserDefaults.standard.set(found.compactMap { $0["id"] as? Int }.max() ?? 0, forKey: seenKey)
            return
        }
        for note in fresh {
            let content = UNMutableNotificationContent()
            content.title = note["title"] as? String ?? "Friday"
            content.body = note["body"] as? String ?? ""
            content.sound = .default
            let request = UNNotificationRequest(identifier: "friday-\(note["id"] ?? 0)", content: content, trigger: nil)
            try? await UNUserNotificationCenter.current().add(request)
        }
        if let newest = found.compactMap({ $0["id"] as? Int }).max(), newest > seen {
            UserDefaults.standard.set(newest, forKey: seenKey)
        }
    }

    /// Notifications newer than the last one shown, oldest first.
    nonisolated static func unseen(_ found: [[String: Any]], after seen: Int) -> [[String: Any]] {
        found.filter { ($0["id"] as? Int ?? 0) > seen }.sorted { ($0["id"] as? Int ?? 0) < ($1["id"] as? Int ?? 0) }
    }

    /// Clicking one brings Friday forward.
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler done: @escaping () -> Void) {
        Task { @MainActor in
            NSApp.activate()
            NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil)
            done()
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound])
    }
}
