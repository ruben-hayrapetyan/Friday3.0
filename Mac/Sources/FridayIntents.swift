import AppIntents

/// Friday's own Siri and Shortcuts commands (C131: "build the siri one"): said to Siri with no shortcut to make
/// first, listed in the Shortcuts app under Friday, and in Spotlight. "New to-do in Friday" asks what it is and reads
/// it the way the add box does ("essay 3h due fri"); "What's next in Friday" says what's on now and next. No phrase is
/// "add … to …": Siri gives those to Reminders (12 Nov: "Add to Friday Test" made a reminder). They need
/// Xcode's App Intents metadata step, which Mac/build.sh runs when Xcode is on the Mac. Friday's links
/// (FridayLink.swift) still work for Shortcuts that open them.

struct AddToFriday: AppIntent {
    static let title: LocalizedStringResource = "New To-do in Friday"
    static let description = IntentDescription("Adds a to-do or an event to Friday, read the way Friday's add box reads it: “essay 3h due fri”.")

    @Parameter(title: "The to-do", requestValueDialog: "What's the to-do?")
    var text: String

    static var parameterSummary: some ParameterSummary {
        Summary("New to-do in Friday: \(\.$text)")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<String> {
        let words = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let said = words.isEmpty ? "Nothing to add." : SiriSays.added(await SiriSays.ask { await Server.post("add", ["text": words]) })
        return .result(value: said, dialog: "\(said)")
    }
}

struct WhatsNext: AppIntent {
    static let title: LocalizedStringResource = "What's Next in Friday"
    static let description = IntentDescription("Says what's on now and what's next on your Friday plan.")

    func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<String> {
        let now = await SiriSays.ask { await Server.get("api/q/now") }
        let said = SiriSays.next(now as? [String: Any], today: SiriSays.today())
        return .result(value: said, dialog: "\(said)")
    }
}

struct FridayShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AddToFriday(),
            phrases: ["New to-do in \(.applicationName)", "New \(.applicationName) to-do", "Give \(.applicationName) a to-do", "Plan something with \(.applicationName)"],
            shortTitle: "New To-do",
            systemImageName: "plus.circle"
        )
        AppShortcut(
            intent: WhatsNext(),
            phrases: ["What's next in \(.applicationName)", "What's next on \(.applicationName)", "Ask \(.applicationName) what's next"],
            shortTitle: "What's Next",
            systemImageName: "clock"
        )
    }
}
