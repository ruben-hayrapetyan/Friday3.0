// A value you step with − and + buttons, tapping quickly (9 Nov: "when i'm clicking quickly to increase/decrease the
// time range on something, and i overshoot and try to go back, it does some weird behavior with the time"). Taps add
// up on the spot and are saved together once you pause. Before, the moment the save went out the number fell back to
// what the server last said until its answer came, so a tap in that gap (going back after an overshoot) counted from
// the old number; and the save's timer restarted whenever the page drew again. Now what you set stays shown until
// the server's own value moves; a save that fails puts back what was there.

import { useEffect, useReducer, useRef } from "react"

export interface Steps {
  pending: number | null // set by your taps, not sent yet
  sent: number | null // sent, shown until the server's value moves from `from`
  from: number | null // the server's value when it was sent
}

export type StepEvent =
  | { kind: "set"; to: number }
  | { kind: "send"; server: number | null }
  | { kind: "server"; value: number | null }
  | { kind: "drop" }

export const NO_STEPS: Steps = { pending: null, sent: null, from: null }

export function steps(s: Steps, e: StepEvent): Steps {
  switch (e.kind) {
    case "set":
      return { ...s, pending: e.to }
    case "send":
      return s.pending === null ? s : { pending: null, sent: s.pending, from: e.server }
    case "server":
      return s.sent !== null && e.value !== s.from ? { ...s, sent: null, from: null } : s
    case "drop":
      return { ...s, sent: null, from: null }
  }
}

/** What to show: your taps, else what you sent, else the server's. */
export const shownOf = (s: Steps, value: number | null) => s.pending ?? s.sent ?? value

const GIVE_UP_MS = 8000 // a sent value the server never confirms stops covering it

export function useSteps(value: number | null, save: (to: number) => unknown, delay: number) {
  const [s, dispatch] = useReducer(steps, NO_STEPS)
  const saveRef = useRef(save)
  saveRef.current = save
  const valueRef = useRef(value)
  valueRef.current = value
  useEffect(() => {
    if (s.pending === null) return
    const to = s.pending
    const timer = setTimeout(() => {
      dispatch({ kind: "send", server: valueRef.current })
      const out = saveRef.current(to)
      if (out instanceof Promise) out.then((r) => r === undefined && dispatch({ kind: "drop" }), () => dispatch({ kind: "drop" }))
    }, delay)
    return () => clearTimeout(timer)
  }, [s.pending, delay])
  useEffect(() => dispatch({ kind: "server", value }), [value])
  useEffect(() => {
    if (s.sent === null) return
    const timer = setTimeout(() => dispatch({ kind: "drop" }), GIVE_UP_MS)
    return () => clearTimeout(timer)
  }, [s.sent])
  return { shown: shownOf(s, value), set: (to: number) => dispatch({ kind: "set", to }), changing: s.pending !== null || s.sent !== null }
}
