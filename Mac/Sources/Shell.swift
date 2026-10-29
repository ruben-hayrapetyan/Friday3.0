import AppKit
import Carbon.HIToolbox
import ServiceManagement
import SwiftUI

/// The Mac app around Friday's website (COMBINED.md 1, 5): one window showing the website, and what a browser can't
/// do — personal's global hotkeys, the live Dock icon (with the count of decisions waiting in the Inbox), opening at
/// login, the menus and the timer in the menu bar. It starts `fridayd` when nothing answers, and stays running with its window closed, so the
/// hotkeys still work.
enum Hotkeys {
    /// Bring Friday up with the to-do drawer open, or tuck it away.
    static let summon = (key: UInt32(kVK_Space), modifiers: UInt32(controlKey | optionKey))
    /// A new event.
    static let newEvent = (key: UInt32(kVK_Space), modifiers: UInt32(optionKey))
    /// Ask Claude.
    static let askClaude = (key: UInt32(kVK_Space), modifiers: UInt32(controlKey))
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let dockIcon = DockIcon()
    private let timer = MenuBarTimer()
    private let badge = DecisionsBadge()
    private let calendars = CalendarBridge()
    private var hotKeys: [GlobalHotKey] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        if TestUser.isTest { dockIcon.ribbon = "TEST" }
        dockIcon.start()
        if !TestUser.isTest, UserDefaults.standard.object(forKey: "hotkeys") as? Bool ?? true {  // yours keeps them
            register(Hotkeys.summon) { [weak self] in self?.toggle() }
            register(Hotkeys.newEvent) { [weak self] in self?.show(then: .newEvent) }
            register(Hotkeys.askClaude) { [weak self] in self?.show(then: .askClaude) }
        }
        Task {
            await Server.shared.ensureRunning()
            timer.start()
            badge.start()
            calendars.start()
        }
        if !TestUser.isTest { LoginItem.enableOnFirstLaunch() }
    }

    func applicationWillTerminate(_ notification: Notification) {
        Server.shared.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if !hasVisibleWindows { show(then: nil) }
        return true
    }

    private func register(_ hotkey: (key: UInt32, modifiers: UInt32), action: @escaping () -> Void) {
        if let made = GlobalHotKey(keyCode: hotkey.key, modifiers: hotkey.modifiers, action: action) {
            hotKeys.append(made)
        }
    }

    private func toggle() {
        if NSApp.isActive, mainWindow?.isVisible == true {
            NSApp.hide(nil)
        } else {
            show(then: .openDrawer)
        }
    }

    func show(then action: HostAction?) {
        NSApp.unhide(nil)
        NSApp.activate()
        mainWindow?.makeKeyAndOrderFront(nil)
        if let action { Page.shared.send(action) }
    }

    private var mainWindow: NSWindow? {
        NSApp.windows.first { $0.identifier?.rawValue.hasPrefix(FridayShell.windowID) ?? false }
    }
}

/// "Open at Login", via the system's login item service: on once for the copy in Applications.
enum LoginItem {
    static var isEnabled: Bool { SMAppService.mainApp.status == .enabled }

    static func set(_ enabled: Bool) {
        try? enabled ? SMAppService.mainApp.register() : SMAppService.mainApp.unregister()
    }

    static func enableOnFirstLaunch() {
        let key = "loginItemConfigured"
        guard !UserDefaults.standard.bool(forKey: key), Bundle.main.bundleURL.path.hasPrefix("/Applications/") else { return }
        UserDefaults.standard.set(true, forKey: key)
        if !isEnabled { try? SMAppService.mainApp.register() }
    }
}

@main
struct FridayShell: App {
    static let windowID = "friday"
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var app

    var body: some Scene {
        Window(TestUser.isTest ? "Friday Test" : "Friday", id: Self.windowID) {
            RootView()
        }
        .defaultSize(width: 1440, height: 900)
        .commands {
            FridayMenus()
            if TestUser.isTest { TestMenu() }
        }

        Settings {
            MacSettings()
        }
    }
}

/// The menu bar: every action the web app has a key for, as Mac menus with Mac shortcuts (COMBINED.md 58).
struct FridayMenus: Commands {
    var body: some Commands {
        CommandGroup(replacing: .newItem) {
            Button("New Event") { Page.shared.send(.newEvent) }.keyboardShortcut("n")
            Button("New To-do") { Page.shared.send(.newTodo) }.keyboardShortcut("n", modifiers: [.command, .shift])
        }
        CommandGroup(after: .textEditing) {
            Button("Search") { Page.shared.send(.search) }.keyboardShortcut("f")
        }
        CommandGroup(before: .toolbar) {  // into the standard View menu, not a second one
            Button("Day") { Page.shared.send(.view("day")) }.keyboardShortcut("1")
            Button("Week") { Page.shared.send(.view("week")) }.keyboardShortcut("2")
            Button("Month") { Page.shared.send(.view("month")) }.keyboardShortcut("3")
            Divider()
            Button("Today") { Page.shared.send(.today) }.keyboardShortcut("t")
            // no ⌘← / ⌘→: in a text field they go to the start and end of the line ([ and ] step the calendar)
            Button("Previous") { Page.shared.send(.previous) }
            Button("Next") { Page.shared.send(.next) }
            Divider()
            Button("To-do Drawer") { Page.shared.send(.drawer) }.keyboardShortcut("t", modifiers: [.command, .control])
        }
        CommandMenu("Go") {
            Button("Plan") { Page.shared.send(.go("/")) }.keyboardShortcut("1", modifiers: [.command, .option])
            Button("To-do") { Page.shared.send(.go("/todo")) }.keyboardShortcut("2", modifiers: [.command, .option])
            Button("Projects & Exams") { Page.shared.send(.go("/projects")) }.keyboardShortcut("3", modifiers: [.command, .option])
            Button("Review") { Page.shared.send(.go("/review")) }.keyboardShortcut("4", modifiers: [.command, .option])
            Button("Inbox") { Page.shared.send(.go("/inbox")) }.keyboardShortcut("5", modifiers: [.command, .option])
            Button("Insights") { Page.shared.send(.go("/insights")) }.keyboardShortcut("6", modifiers: [.command, .option])
            Button("Rules") { Page.shared.send(.go("/rules")) }.keyboardShortcut("7", modifiers: [.command, .option])
            Button("Friday Settings") { Page.shared.send(.go("/settings")) }.keyboardShortcut(",", modifiers: [.command, .option])
        }
        CommandGroup(replacing: .help) {
            Button("Friday Tour") { Page.shared.send(.tour) }
            Button("Set Up Friday…") { Page.shared.send(.setup) }
            Button("Shortcuts") { Page.shared.send(.go("/settings/shortcuts")) }
        }
        CommandMenu("Plan") {
            Button("Ask Claude…") { Page.shared.send(.askClaude) }.keyboardShortcut("j")
            Button("Other Ways…") { Page.shared.send(.otherWays) }
            Button("What Gives…") { Page.shared.send(.triage) }
            Divider()
            Button("Shove…") { Page.shared.send(.shove) }
            Button("Pace…") { Page.shared.send(.pace) }
            Button("Morning Brief") { Page.shared.send(.brief) }
        }
    }
}

/// The Mac app's own settings (COMBINED.md 60): the rest are on the website's Settings page.
struct MacSettings: View {
    @AppStorage("hotkeys") private var hotkeys = true
    @AppStorage("menuBarTimer") private var menuBarTimer = true
    @AppStorage("macCalendars") private var macCalendars = true
    @AppStorage("fridaydPath") private var fridaydPath = ""
    @State private var opensAtLogin = LoginItem.isEnabled

    var body: some View {
        Form {
            if TestUser.isTest {
                Text("Friday Test leaves the global shortcuts and opening at login to your Friday, and never changes a "
                     + "real calendar: this Mac's and Google's are only read.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Toggle("Global shortcuts: ⌃⌥Space Friday, ⌥Space new event, ⌃Space Ask Claude", isOn: $hotkeys)
                Text("Takes effect the next time Friday opens.").font(.caption).foregroundStyle(.secondary)
            }
            Toggle("The running timer in the menu bar", isOn: $menuBarTimer)
            Toggle("Send this Mac's calendars to Friday", isOn: $macCalendars)
            Text("Choose which ones Friday reads in Settings → Calendars. Takes effect the next time Friday opens.")
                .font(.caption).foregroundStyle(.secondary)
            if !TestUser.isTest {
                Toggle("Open at login", isOn: Binding(get: { opensAtLogin }, set: { LoginItem.set($0); opensAtLogin = LoginItem.isEnabled }))
            }
            HStack {
                TextField("fridayd", text: $fridaydPath, prompt: Text(Server.shared.executable?.path ?? "~/.local/bin/fridayd"))
                Button("Choose…") {
                    let panel = NSOpenPanel()
                    panel.canChooseDirectories = false
                    if panel.runModal() == .OK, let url = panel.url { fridaydPath = url.path }
                }
            }
            Text("Friday's server. Found in ~/.local/bin or the Friday-planner checkout when left empty.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(20)
        .frame(width: 560)
    }
}
