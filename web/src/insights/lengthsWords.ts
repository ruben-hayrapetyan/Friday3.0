// What Insights says of learning how long things take before it has (22 Nov: a tester with 14 timed things was told
// Friday needed a few more; the learner counts only what's timed on a usual day, not on a break or at another pace).

export interface LengthsSoFar {
  have?: number
  need?: number
  aside?: number
}

const aside = (n: number) => (n ? ` ${n} timed on a break or at another pace ${n === 1 ? "doesn't" : "don't"} count.` : "")

/** Insights' "So far" row. */
export function soFarWords({ have = 0, need = 5, aside: off = 0 }: LengthsSoFar): string {
  if (have >= need) return `${have} finished things timed: Friday is learning from them now.`
  return `${have} of ${need} finished things timed. Use Start on a task to time it.${aside(off)}`
}

/** Under "Adjust new estimates automatically", before anything is learned. */
export function switchWords({ have = 0, need = 5, aside: off = 0 }: LengthsSoFar): string {
  if (have >= need) return "Friday is learning from what you timed now."
  const more = need - have
  return `Friday needs ${more} more timed ${more === 1 ? "thing" : "things"} before it can.${aside(off)}`
}
