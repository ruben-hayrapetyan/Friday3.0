// What the calendar draws (COMBINED.md 19): a calendar you gave a title-row button, and what the categories' filter
// matches (office hours), stay off the calendar until you switch them on: not drawn, not even dashed, in the grid,
// the month, the day's agenda or the mini month. An event on two of your calendars at once (the same title and
// times) is drawn once. None of this changes what's planned. In What if with changes staged, the calendar draws the
// plan with them (`whatif/store.ts`).

import { useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { query, type Schemas } from "@/api/client"
import { useSettings } from "@/hooks/queries"
import { useShell } from "@/shell/ShellContext"
import { useTrial, useWhatIf, within } from "@/whatif/store"
import { useLook } from "@/theme/LookProvider"

export interface Showing {
  toolbar: string[] // calendars with a title-row button
  showing: string[] // of those, the ones switched on
  showFiltered: boolean // the filter's events switched on
}

type Event = { calendar?: string | null; filtered?: boolean }

export function shown(event: Event, s: Showing): boolean {
  if (event.filtered && !s.showFiltered) return false
  return !(event.calendar && s.toolbar.includes(event.calendar) && !s.showing.includes(event.calendar))
}

export function withShown(plan: Schemas["PlanOut"], s: Showing): Schemas["PlanOut"] {
  const seen = new Set<string>()
  const fixed = plan.fixed.filter((f) => {
    if (!shown(f, s)) return false
    const key = `${f.title}\u0000${f.start}\u0000${f.end}`
    if (seen.has(key)) return false // the same event on another calendar
    seen.add(key)
    return true
  })
  return fixed.length === plan.fixed.length ? plan : { ...plan, fixed }
}

export function useShowing(): Showing {
  const settings = useSettings().data as { calendar_look?: { toolbar?: string[] } } | undefined
  const { look } = useLook()
  return { toolbar: settings?.calendar_look?.toolbar ?? [], showing: look.showing, showFiltered: look.showFiltered }
}

/** The plan as the calendar draws it. */
export function useShownPlan(start: string, end: string) {
  const s = useShowing()
  const key = `${s.toolbar.join("|")}/${s.showing.join("|")}/${s.showFiltered}`
  const select = useCallback((plan: Schemas["PlanOut"]) => withShown(plan, s), [key])
  const real = useQuery({ queryKey: ["plan", start, end], queryFn: () => query("plan", { start, end }), select })
  const w = useWhatIf()
  const trial = useTrial(useShell().today).data
  if (w.on && w.changes.length && trial) return { ...real, data: withShown(within(trial.plan, start, end), s) }
  return real
}
