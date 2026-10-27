import AppKit

/// The decisions waiting in Friday's Inbox, as a count on the Dock icon (27 Oct: "remove notifications… decisions but
/// in the inbox with a notification symbol and a way to let the user know to actually go check it"). The Mac's own
/// notifications went with the rest: nothing pops up, the count stays until you answer.
@MainActor
final class DecisionsBadge {
    private var poll: Timer?

    func start() {
        poll = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
            Task { @MainActor in await self.check() }
        }
        Task { await check() }
    }

    private func check() async {
        guard let status = await Server.get("api/q/status") as? [String: Any] else { return }
        NSApp.dockTile.badgeLabel = DecisionsBadge.label(status)
    }

    /// The count to show, or nothing when nothing waits.
    nonisolated static func label(_ status: [String: Any]) -> String? {
        let waiting = (status["decisions"] as? [Any])?.count ?? 0
        return waiting > 0 ? String(waiting) : nil
    }
}
