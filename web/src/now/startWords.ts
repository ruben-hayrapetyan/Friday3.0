// One way to start a task wherever it's started (24 Nov, a user: from To-do, while timing another, "it pauses the
// current task instead of giving the option to do alongside"): when something else is being timed, the start is a
// Switch that says it stops that, with Alongside beside it, as the plan's block has had since 2 Nov.

export interface StartWords {
  label: string // "Switch", or "Resume"/"Start" (or the page's own word for it) when nothing else is timed
  hint: string // what pressing it does
  alongside: boolean // whether Alongside goes beside it
}

/** The start button's words: `other` is what's being timed now (not this), `worked` whether it has time already. */
export function startWords(other: string | null | undefined, worked: boolean, start = "Start"): StartWords {
  if (other) return { label: "Switch", hint: `Times this instead: ${other} stops`, alongside: true }
  return { label: worked ? "Resume" : start, hint: "Times it now", alongside: false }
}

/** What's being timed now other than `id`: the timer's, else one timed alongside. */
type Timed = { item_id: number | null; title?: string | null }

export function otherTimed(status: { timer?: Timed | null; alongside?: Timed[] | null } | undefined, id: number): string | null {
  const running = [status?.timer, ...(status?.alongside ?? [])].filter((t): t is Timed => !!t && t.item_id !== null)
  if (running.some((t) => t.item_id === id)) return null // this one's being timed: nothing to switch from
  const other = running.find((t) => t.item_id !== id)
  return other ? (other.title ?? "what you're on") : null
}
