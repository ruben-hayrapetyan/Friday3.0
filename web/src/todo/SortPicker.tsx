// How the list is sorted, as a short menu of choices that say what they do, in place of a bare dropdown.

import { Icon } from "@/components/fr/controls"
import type { SortBy } from "./groups"

export const SORT_CHOICES: { value: SortBy; icon: string; says: string }[] = [
  { value: "Next up", icon: "clock", says: "When Friday plans it" },
  { value: "Due date", icon: "flag", says: "Soonest deadline first" },
  { value: "Length", icon: "hourglass-medium", says: "Longest first" },
  { value: "Title", icon: "text-aa", says: "A to Z" },
]

export function SortPicker({ value, onPick, compact }: { value: SortBy; onPick: (v: SortBy) => void; compact?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Sort" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {SORT_CHOICES.map((c) => {
        const on = c.value === value
        return (
          <button
            key={c.value}
            role="radio"
            aria-checked={on}
            onClick={() => onPick(c.value)}
            className="fr-plain fr-hover"
            style={{
              display: "grid",
              gridTemplateColumns: "18px minmax(0,1fr) 14px",
              gap: 8,
              alignItems: "center",
              padding: compact ? "4px 6px" : "6px 8px",
              borderRadius: "var(--radius-sm)",
              textAlign: "left",
              background: on ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined,
            }}
          >
            <Icon name={c.icon} size={14} style={{ color: on ? "var(--color-accent-300)" : "var(--color-neutral-400)" }} />
            <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              <span style={{ fontSize: 13, color: on ? "var(--color-text)" : "var(--color-neutral-200)" }}>{c.value}</span>
              {!compact && <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>{c.says}</span>}
            </span>
            {on && <Icon name="check" size={12} style={{ color: "var(--color-accent-300)" }} />}
          </button>
        )
      })}
    </div>
  )
}
