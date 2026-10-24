// Picture cards for a setting's options: each choice shows a small drawing of what it looks like and a short name
// under it, the chosen one ringed in the accent. Cards wrap to the width they have, three across on a phone.

import type { ReactNode } from "react"
import { Icon } from "@/components/fr/controls"

export interface Choice<T extends string> {
  value: T
  label: string
  art: ReactNode
}

export function ChoiceCards<T extends string>(props: { choices: readonly Choice<T>[]; value: T; onPick: (value: T) => void; label: string }) {
  const { choices, value, onPick, label } = props
  return (
    <div role="group" aria-label={label} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 100px), 1fr))", gap: 10, maxWidth: 560 }}>
      {choices.map((c) => {
        const on = c.value === value
        return (
          <button
            key={c.value}
            type="button"
            aria-pressed={on}
            onClick={() => onPick(c.value)}
            className="fr-plain fr-hover-soft"
            style={{
              position: "relative",
              display: "flex",
              flexDirection: "column",
              gap: 6,
              minWidth: 0,
              padding: 5,
              borderRadius: "var(--radius-md)",
              boxShadow: on ? "inset 0 0 0 2px var(--color-accent)" : "inset 0 0 0 1px var(--fr-rule)",
            }}
          >
            <span
              aria-hidden
              style={{ position: "relative", display: "block", width: "100%", aspectRatio: "5 / 3", containerType: "inline-size", overflow: "hidden", borderRadius: 5, background: "var(--color-bg)", boxShadow: "inset 0 0 0 1px var(--fr-hairline)" }}
            >
              {c.art}
            </span>
            {on && (
              <span aria-hidden style={{ position: "absolute", top: 8, right: 8, display: "grid", placeItems: "center", width: 16, height: 16, borderRadius: "50%", background: "var(--color-accent)", color: "var(--fr-ink)", boxShadow: "0 0 0 2px var(--color-bg)" }}>
                <Icon name="check" size={10} style={{ fontWeight: 700 }} />
              </span>
            )}
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 18, fontSize: 12, lineHeight: 1.2, textAlign: "center", fontWeight: on ? 500 : 400, color: on ? "var(--color-text)" : "var(--color-neutral-300)" }}>
              {c.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
