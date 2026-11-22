// The suggestions you answered in the Inbox, kept outside the page (22 Nov: accepted quickly, one after another, they
// looked unanswered while Friday saved them; the Inbox left and opened again showed them waiting, and accepting them a
// second time said "no pending suggestion"). Each stays answered while Friday saves it and until the server's list no
// longer has it; one Friday refuses goes back to waiting.

import { useSyncExternalStore } from "react"
import type { Schemas } from "@/api/client"

export interface Answer {
  s: Schemas["SuggestionOut"]
  accepted: boolean
  commandId: number | null // null while Friday saves it
}

let answers: Answer[] = []
const listeners = new Set<() => void>()
const changed = (next: Answer[]) => {
  answers = next
  for (const tell of listeners) tell()
}

export const answersNow = (): Answer[] => answers

export function answer(rs: Answer[]): void {
  changed([...answers.filter((r) => !rs.some((x) => x.s.id === r.s.id)), ...rs])
}

export function unanswer(id: number): void {
  if (answers.some((r) => r.s.id === id)) changed(answers.filter((r) => r.s.id !== id))
}

/** A new visit to the Inbox: answers the server has taken (gone from its list of `waiting`) are let go; those still
 * being saved, or still on its list, stay answered. `all` (tests) lets every one go. */
export function forgetTaken(waiting: Set<number>, all = false): void {
  const kept = all ? [] : answers.filter((r) => r.commandId === null || waiting.has(r.s.id))
  if (kept.length !== answers.length) changed(kept)
}

const subscribe = (tell: () => void) => (listeners.add(tell), () => void listeners.delete(tell))

export const useAnswers = (): Answer[] => useSyncExternalStore(subscribe, answersNow)
