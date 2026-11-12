import AppIntents

/// Friday's own Siri and Shortcuts commands (C131: "build the siri one"): said to Siri with no shortcut to make
/// first, listed in the Shortcuts app under Friday, and in Spotlight. "Add to Friday" asks what to add and reads it
/// the way the add box does ("essay 3h due fri"); "What's next in Friday" says what's on now and next. They need
/// Xcode's App Intents metadata step, which Mac/build.sh runs when Xcode is on the Mac. Friday's links
/// (FridayLink.swift) still work for Shortcuts that open them.

struct AddToFriday: AppIntent {
    static let title: LocalizedStringResource = "Add to Friday"
    static let description = IntentDescription("Adds a to-do or an event to Friday, read the way Friday's add box reads it: “essay 3h due fri”.")

    @Parameter(title: "What to add", requestValueDialog: "What should I add?")
    var text: String

    static var parameterSummary: some ParameterSummary {
        Summary("Add \(\.$text) to Friday")
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
            phrases: ["Add to \(.applicationName)", "Add a to-do to \(.applicationName)", "New \(.applicationName) to-do"],
            shortTitle: "Add to Friday",
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
