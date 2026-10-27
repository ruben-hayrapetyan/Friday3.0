// Which task an event's time is likely for (27 Oct: "A4dd" on the calendar is when you'll write "CS A4 Design Doc").
// A word of the task's title found in the event's ("A4"), and the initials of a run of its words ("dd" for "design
// doc"), each count; a word with a digit counts double. Friday asks about the one that counts most, and only when it
// counts enough and nothing else counts as much.

export interface Task {
  id: number
  title: string
}

const words = (title: string) => title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)
const squashed = (title: string) => title.toLowerCase().replace(/[^a-z0-9]/g, "")

/** How much a task's title is in an event's. */
export function likeness(event: string, task: string): number {
  const e = squashed(event)
  const ws = words(task)
  let score = 0
  for (const w of ws) if ((/\d/.test(w) || w.length >= 3) && e.includes(w)) score += /\d/.test(w) ? 2 : 1
  for (let i = 0; i < ws.length; i++) {
    for (let j = i + 2; j <= ws.length; j++) {
      const initials = ws.slice(i, j).map((w) => w[0]).join("")
      if (e.includes(initials) && !ws.includes(initials)) score += 1
    }
  }
  return score
}

/** The task an event is most likely for, or null when none is clearly. */
export function likelyTask<T extends Task>(event: string, tasks: T[]): T | null {
  const scored = tasks.map((t) => ({ t, score: likeness(event, t.title) })).sort((a, b) => b.score - a.score)
  const [first, second] = scored
  if (!first || first.score < 2 || (second && second.score === first.score)) return null
  return first.t
}

/** The tasks to offer for an event, the likeliest first. */
export function ranked<T extends Task>(event: string, tasks: T[]): T[] {
  return [...tasks].sort((a, b) => likeness(event, b.title) - likeness(event, a.title))
}
