// What a full preview would change (DESIGN §9.2): the pace sheet and the settings screen show it before Apply.

import type { Schemas } from "@/api/client"
import { lines, summary } from "@/lib/changes"

export function ChangeList({ changes, today, busy }: { changes?: Schemas["ChangeOut"] | null; today: string; busy?: boolean }) {
  if (!changes) return <p className="text-sm text-muted-foreground">{busy ? "Working out what would move…" : ""}</p>
  const shown = lines(changes, today)
  return (
    <div className={`space-y-1 text-sm ${busy ? "opacity-60" : ""}`}>
      <p className="font-medium">{summary(changes)}</p>
      {(changes.notices ?? []).map((n) => (
        <p key={n} className="text-amber-700 dark:text-amber-300">
          {n}
        </p>
      ))}
      <ul className="max-h-48 overflow-y-auto text-xs">
        {shown.map((l) => (
          <li key={l.title} className="flex justify-between gap-3 py-0.5">
            <span className="truncate">{l.title}</span>
            <span className="shrink-0 text-muted-foreground">{l.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
