// What the calendar draws (COMBINED.md 19): a calendar you hid (it has a Show button in the title row), and what the
// categories' filter matches (office hours), stay off the calendar until you switch them on: not drawn, not even
// dashed, in the grid or the month. A hidden calendar is ignored everywhere else (14 Nov: a client hid calendars in
// the walk and their invitations still reached the Inbox): the server leaves its events out of every other answer
// (planner/hidden.py) and marks them `hidden_calendar` in the plan, which only the calendar asks for (`with_hidden`);
// the sidebar's day and mini month leave them out even while they're switched on (`quiet`). An event on two of your
// calendars at once (the same title and times) is drawn once. None of this changes what's planned. In What if with
// changes staged, the calendar draws the plan with them (`whatif/store.ts`).

import { useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import type { Schemas } from "@/api/client"
import { planWithHidden, useSettings } from "@/hooks/queries"
import { useShell } from "@/shell/ShellContext"
import { trialView, useTrial, useWhatIf, within } from "@/whatif/store"
import { useLook } from "@/theme/LookProvider"
import { usePending } from "./pending"

export interface Showing {
  toolbar: string[] // calendars with a title-row button
  showing: string[] // of those, the ones switched on
  showFiltered: boolean // the filter's events switched on
  showPastPlan: boolean // Friday's plan for the past (done, missed, timed over); off, only when you worked shows
}

type Event = { calendar?: string | null; filtered?: boolean; hidden_calendar?: string | null }

/** The calendar you hid that an event is on: as the server marked it (any kind of calendar, a calendar link too),
 * or by its calendar's name, which follows a Hide at once, before the server answers again. */
export function hiddenOn(event: Event, toolbar: string[]): string | null {
  return event.hidden_calendar ?? (event.calendar && toolbar.includes(event.calendar) ? event.calendar : null)
}

export function shown(event: Event, s: Showing): boolean {
  if (event.filtered && !s.showFiltered) return false
  const hidden = hiddenOn(event, s.toolbar)
  return !hidden || s.showing.includes(hidden)
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
  // 2 Nov: "i want it to show when i worked i just don't want it to show its own schedule": off, every block whose
  // time has gone (it has a state) is left out; the sessions you timed (plan.sessions) stay
  const blocks = s.showPastPlan ? plan.blocks : plan.blocks.filter((b) => !b.state)
  return fixed.length === plan.fixed.length && blocks.length === plan.blocks.length ? plan : { ...plan, fixed, blocks }
}

export function useShowing(): Showing {
  const settings = useSettings().data as { calendar_look?: { toolbar?: string[]; show_past_plan?: boolean } } | undefined
  const { look } = useLook()
  const showPastPlan = settings?.calendar_look?.show_past_plan ?? true
  return { toolbar: settings?.calendar_look?.toolbar ?? [], showing: look.showing, showFiltered: look.showFiltered, showPastPlan }
}

/** The plan as the calendar draws it; `quiet`, without a hidden calendar even while it's switched on under Show (the
 * sidebar's day and mini month: only the calendar shows it). */
export function useShownPlan(start: string, end: string, { quiet = false } = {}) {
  const showing = useShowing()
  const s = quiet ? { ...showing, showing: [] } : showing
  const key = `${s.toolbar.join("|")}/${s.showing.join("|")}/${s.showFiltered}/${s.showPastPlan}`
  const select = useCallback((plan: Schemas["PlanOut"]) => withShown(plan, s), [key])
  const fetched = useQuery({ queryKey: ["plan", start, end], queryFn: () => planWithHidden(start, end), select })
  const real = usePending(fetched)
  const w = useWhatIf()
  const trial = useTrial(useShell().today)
  if (!w.on || !w.changes.length || !real.data) return real
  // While trying: the latest answer with the changes made since drawn at once (whatif/store.trialView).
  const view = trialView(real.data, trial.out, w.changes, trial.answered)
  return { ...real, data: { ...withShown(within(view, start, end), s), tried: view.tried } }
}
