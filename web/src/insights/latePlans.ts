// Late on paper, on time in practice (2 Nov: "it consistently proposes schedules that have things late but i don't do
// anything late"): what Insights says of the work your plans showed late that you finished by its due (3 Nov:
// `beat_plan` had no screen; only its Inbox questions showed).

export const WAYS: Record<string, string> = {
  faster: "took less time than planned",
  nights: "worked later at night",
  mornings: "started earlier in the morning",
  events: "worked through events",
  daytime: "used free time in the day",
  untold: "in ways Friday couldn't see",
}

/** How you did it, the most used first (ties in WAYS' order), each with how many times: "worked through events · 7". */
export function ways(counts: Record<string, number>): { way: string; said: string; n: number }[] {
  const order = Object.keys(WAYS)
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .sort(([a, x], [b, y]) => y - x || order.indexOf(a) - order.indexOf(b))
    .map(([way, n]) => ({ way, said: WAYS[way] ?? way, n }))
}

/** The headline: how often a plan's lateness didn't happen. */
export function headline(onTime: number, late: number): string {
  const all = onTime + late
  if (!all) return "No work your plans showed late has come due yet."
  const share = Math.round((onTime / all) * 100)
  return `${onTime} of ${all} things your plans showed late you finished on time (${share}%).`
}
