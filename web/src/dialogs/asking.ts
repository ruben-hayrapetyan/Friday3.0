// A question to your AI that outlives its window (3 Nov, the CS 2112 UI lecture: past ten seconds "the app must
// support parallel activities"; an answer could take up to three minutes behind a bare "Asking…"). You see the
// seconds go by and can stop waiting; you can close the window and keep working, and when the answer comes Friday
// says so and opens it again. The rules are pure functions here; the one question in flight is kept below.

import { useSyncExternalStore } from "react"
import type { Schemas } from "@/api/client"

type Answer = Schemas["AskClaudeOut"]

export interface Asking {
  id: number
  text: string
  purpose: "anything" | "rule"
  began: number // ms
  state: "asking" | "answered" | "failed" | "stopped"
  answer?: Answer
  error?: string
}

export const begin = (text: string, purpose: Asking["purpose"], now: number, id: number): Asking => ({ id, text, purpose, began: now, state: "asking" })

/** An answer, for the question still waited on; one for a question stopped or replaced is dropped. */
export function settle(was: Asking | null, id: number, answer: Answer): Asking | null {
  return was && was.id === id && was.state === "asking" ? { ...was, state: "answered", answer } : was
}

export function fail(was: Asking | null, id: number, error: string): Asking | null {
  return was && was.id === id && was.state === "asking" ? { ...was, state: "failed", error } : was
}

export function stop(was: Asking | null, id: number): Asking | null {
  return was && was.id === id && was.state === "asking" ? { ...was, state: "stopped" } : was
}

/** "Asking Gemini… 12s", and once it's slow, that you needn't wait. */
export function waiting(seconds: number, ai: string): { line: string; note: string | null } {
  const s = Math.max(0, Math.floor(seconds))
  const line = `Asking ${ai}… ${s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`}`
  return { line, note: s >= 8 ? "You can close this and keep working: Friday says when the answer comes." : null }
}

// The one question in flight, shared by every Ask window.
let current: Asking | null = null
let controller: AbortController | null = null
let windowOpen = false
const listeners = new Set<() => void>()
const set = (next: Asking | null) => {
  current = next
  for (const l of listeners) l()
}

export const asking = {
  get: () => current,
  begin(text: string, purpose: Asking["purpose"]): { id: number; signal: AbortSignal } {
    controller?.abort() // a new question replaces one still waited on
    controller = new AbortController()
    const id = Date.now() + Math.random()
    set(begin(text, purpose, Date.now(), id))
    return { id, signal: controller.signal }
  },
  settle: (id: number, answer: Answer) => set(settle(current, id, answer)),
  fail: (id: number, error: string) => set(fail(current, id, error)),
  stop(id: number) {
    if (current?.id === id) controller?.abort()
    set(stop(current, id))
  },
  /** Seen: the window showed it, so it isn't kept to show again. */
  clear: () => set(current && current.state === "asking" ? current : null),
  open: (on: boolean) => (windowOpen = on),
  isOpen: () => windowOpen,
}

export function useAsking(): Asking | null {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => current,
  )
}
