// Your week (pace.weekly): a pace for some weekdays, every week ("go easier on Saturdays, harder on Sundays"). A day
// is a button that steps through the paces; the default pace means nothing set. A pace picked for some dates in
// Pace comes before this.

import { useCommand } from "@/hooks/useCommand"
import { usePaces, useSettings } from "@/hooks/queries"

const DAYS: [string, string][] = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
]

export function WeekPaces({ compact = false }: { compact?: boolean }) {
  const paces = usePaces().data
  const settings = useSettings().data as Record<string, { weekly?: Record<string, string> }> | undefined
  const save = useCommand("settings_set", { label: () => "Saved your week" })
  if (!paces) return null
  const weekly = settings?.pace?.weekly ?? {}
  const names = [paces.default, ...Object.keys(paces.paces).filter((p) => p !== paces.default)]
  const next = (day: string) => {
    const now = weekly[day] ?? paces.default
    const then = names[(names.indexOf(now) + 1) % names.length]
    const { [day]: _, ...rest } = weekly
    save({ key: "pace", value: { weekly: then === paces.default ? rest : { ...rest, [day]: then } } })
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: compact ? 4 : 6 }}>
      {DAYS.map(([day, label]) => {
        const pace = weekly[day] ?? paces.default
        const set = pace !== paces.default
        return (
          <button
            key={day}
            className="fr-plain fr-press"
            onClick={() => next(day)}
            title={`${label}: ${pace} every week. Click to change.`}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              padding: compact ? "5px 2px" : "8px 4px",
              borderRadius: "var(--radius-md)",
              background: set ? "color-mix(in srgb, var(--color-accent) 16%, transparent)" : "var(--color-surface)",
              boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)",
            }}
          >
            <span style={{ fontSize: 11, color: "var(--color-neutral-400)" }}>{label}</span>
            <span style={{ fontSize: compact ? 11 : 12, fontWeight: set ? 500 : 400, color: set ? "var(--color-accent-200)" : "var(--color-neutral-500)" }}>{pace}</span>
          </button>
        )
      })}
    </div>
  )
}
