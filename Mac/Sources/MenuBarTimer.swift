import AppKit

/// The running timer in the menu bar (COMBINED.md 31): what you're timing and for how long, with Pause and Done, so
/// it's in sight with Friday's window away. Hidden while nothing is timed.
@MainActor
final class MenuBarTimer: NSObject {
    private var item: NSStatusItem?
    private var poll: Timer?
    private var tick: Timer?
    private var title = ""
    private var since: Date?

    func start() {
        poll = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            Task { @MainActor in await self.refresh() }
        }
        Task { await refresh() }
    }

    private func refresh() async {
        guard UserDefaults.standard.object(forKey: "menuBarTimer") as? Bool ?? true,
              let status = await Server.status(),
              let timer = status["timer"] as? [String: Any],
              let elapsed = (timer["elapsed_s"] as? NSNumber)?.doubleValue else {
            hide()
            return
        }
        let item = (timer["item_id"] as? Int).map { "api/q/item?id=\($0)" }
        let found = item == nil ? nil : await Server.get(item!) as? [String: Any]
        title = ((found?["item"] as? [String: Any])?["title"] as? String) ?? "Timing"
        since = Date().addingTimeInterval(-elapsed)
        show()
    }

    private func show() {
        if item == nil {
            item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            let menu = NSMenu()
            menu.addItem(withTitle: "Pause", action: #selector(pause), keyEquivalent: "").target = self
            menu.addItem(withTitle: "Done", action: #selector(done), keyEquivalent: "").target = self
            menu.addItem(.separator())
            menu.addItem(withTitle: "Open Friday", action: #selector(open), keyEquivalent: "").target = self
            item?.menu = menu
            tick = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
                Task { @MainActor in self.draw() }
            }
        }
        draw()
    }

    private func draw() {
        guard let since else { return }
        item?.button?.title = MenuBarTimer.label(title: title, seconds: Date().timeIntervalSince(since))
    }

    /// "● Essay 1:02:03", the title cut to keep the menu bar tidy.
    nonisolated static func label(title: String, seconds: Double) -> String {
        let s = max(0, Int(seconds))
        let clock = s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
                              : String(format: "%d:%02d", s / 60, s % 60)
        let short = title.count > 24 ? String(title.prefix(23)) + "…" : title
        return "● \(short) \(clock)"
    }

    private func hide() {
        tick?.invalidate()
        tick = nil
        if let item { NSStatusBar.system.removeStatusItem(item) }
        item = nil
    }

    @objc private func pause() { Task { await Server.post("stop"); await refresh() } }
    @objc private func done() { Task { await Server.post("stop", ["done": true]); await refresh() } }
    @objc private func open() { NSApp.activate(); NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil) }
}
