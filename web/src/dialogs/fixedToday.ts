// The brief's "Fixed today" (C36: "the morning brief lists whole-day events at 12am"): a whole-day event has no time
// of day, so it reads "All day" and comes first, as the week's header puts it above the day's hours.

import { clock } from "@/lib/format"
import { isWholeDay } from "@/plan/wholeDay"

type Fixed = { start?: string | null; end?: string | null }

/** Today's fixed items in the brief's order, each with the time it shows: whole-day ones first, the rest by start. */
export function fixedToday<T extends Fixed>(fixed: T[]): { item: T; time: string }[] {
  const whole = fixed.filter(isWholeDay)
  const timed = fixed.filter((f) => !isWholeDay(f)).sort((a, b) => (a.start ?? "").localeCompare(b.start ?? ""))
  return [
    ...whole.map((item) => ({ item, time: "All day" })),
    ...timed.map((item) => ({ item, time: item.start ? clock(item.start) : "" })),
  ]
}
