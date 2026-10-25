// What's already been answered for a day's blocks: what Friday has on record (an earlier review, or a block settled
// from the calendar), with this visit's answers over it. Coming back to a reviewed day used to start it over, since
// only this tab's answers counted and they were cleared on submit.

import type { Block } from "@/api/client"
import { toMin } from "@/lib/time"

export type Status = "done" | "partial" | "not_done" | "finished"
export interface Answer {
  status: Status
  minutes: number
}

export const length = (b: Block) => toMin(b.end) - toMin(b.start)

/** An answer on record, read back from the minutes it logged: none, all of the block, or some of it. */
export function onRecord(cards: Block[], settled: Record<string, number> | undefined): Record<string, Answer> {
  const out: Record<string, Answer> = {}
  for (const b of cards) {
    const minutes = settled?.[b.key]
    if (minutes === undefined) continue
    out[b.key] = { status: minutes <= 0 ? "not_done" : minutes >= length(b) ? "done" : "partial", minutes }
  }
  return out
}

/** The day's answers so far; `fresh` answers it all again, ignoring what's on record. */
export function known(cards: Block[], settled: Record<string, number> | undefined, answers: Record<string, Answer>, fresh: boolean): Record<string, Answer> {
  return fresh ? answers : { ...onRecord(cards, settled), ...answers }
}
