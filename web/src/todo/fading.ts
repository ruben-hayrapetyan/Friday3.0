// Work that matters less the longer it's overdue (3 Nov: "have the importance of doing a reading on time deteriorate
// as time goes on"), said on a task's page under "After it's due". Same maths as settings `FadingLate.factor`.

/** What's left of its importance `days` late: 1 on time, ½ one half-life late. */
export function left(days: number, halfLife: number): number {
  return 0.5 ** (Math.max(0, days) / halfLife)
}

/** "Planned late, mattering half as much for every 3 days late (a week late, about a fifth)." */
export function fadingSaid(kind: string | null | undefined, halfLife: number): string {
  const days = halfLife === 1 ? "day" : `${Number(halfLife.toFixed(1))} days`
  const week = Math.round(left(7, halfLife) * 100)
  const as = kind ? `As for all ${kind.toLowerCase()}s: p` : "P"
  return `${as}lanned late if it can't be on time, mattering half as much for every ${days} late (a week late, ${week}%), so work still on time comes first.`
}
