// Shortcuts (v22): what the keyboard does.

import { SectionHead } from "./SettingsPage"

const KEYS: [string, string[]][] = [
  ["Search everything", ["⌘", "K"]],
  ["Add a to-do", ["N"]],
  ["Shove: take time back", ["S"]],
  ["Change pace", ["P"]],
  ["Start or pause the timer", ["Space"]],
  ["Day, 3 days or week", ["D", "3", "W"]],
  ["Earlier or later period", ["[", "]"]],
  ["Show or hide the to-do list", ["T"]],
  ["Move the selected block by 15 minutes", ["↑", "↓"]],
  ["Undo", ["⌘", "Z"]],
  ["Close a panel", ["Esc"]],
  ["Answer a review card", ["1", "2", "3", "4"]],
  ["Accept, edit or reject in the Inbox", ["A", "E", "R"]],
]

export function Shortcuts() {
  return (
    <>
      <SectionHead title="Shortcuts" note="Everything on the plan works from the keyboard." />
      {KEYS.map(([action, keys]) => (
        <div key={action} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 24, alignItems: "center", padding: "12px 0" }}>
          <span>{action}</span>
          <span style={{ display: "flex", gap: 4 }}>
            {keys.map((k) => (
              <kbd key={k} style={{ minWidth: 24, padding: "2px 7px", borderRadius: 6, background: "var(--color-bg)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent), 0 1px 0 color-mix(in srgb, var(--color-text) 14%, transparent)", font: "inherit", fontSize: 12, textAlign: "center" }}>
                {k}
              </kbd>
            ))}
          </span>
        </div>
      ))}
    </>
  )
}
