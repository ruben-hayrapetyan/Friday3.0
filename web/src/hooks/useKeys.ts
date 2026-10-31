// Keyboard shortcuts (DESIGN §18.10). Single keys work only when nothing that takes text or a dialog has focus.

import { useEffect, useRef } from "react"

export type KeyAction =
  | "quickAdd"
  | "palette"
  | "day"
  | "three"
  | "week"
  | "month"
  | "previous"
  | "next"
  | "drawer"
  | "shove"
  | "pace"
  | "timer"
  | "undo"
  | "earlier"
  | "later"
  | "open"

const SINGLE: Record<string, KeyAction> = {
  n: "quickAdd",
  d: "day",
  "3": "three",
  w: "week",
  m: "month",
  "[": "previous",
  "]": "next",
  t: "drawer",
  s: "shove",
  p: "pace",
  " ": "timer",
  ArrowUp: "earlier",
  ArrowDown: "later",
  Enter: "open",
}

export interface KeyPress {
  key: string
  meta: boolean // ⌘ on a Mac, Ctrl elsewhere
  alt: boolean
  busy: boolean // focus is in a text field, a dialog or a control that uses the key itself
  modal?: boolean // something is open over the page (setup, a dialog): even ⌘K waits
}

export function keyAction({ key, meta, alt, busy, modal }: KeyPress): KeyAction | null {
  if (modal) return null // the audit (31 Oct): under setup, Space ran the timer and ⌘K swapped setup for search
  if (meta && (key.toLowerCase() === "k" || key.toLowerCase() === "f")) return "palette" // one search (COMBINED.md 57)
  if (busy || alt) return null
  if (meta) return key.toLowerCase() === "z" ? "undo" : null
  return SINGLE[key] ?? null
}

function busy(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target.closest("input, textarea, select, [role=dialog], [role=menu]")) return true
  // they press the focused button, or what acts as one (a block on the calendar, a to-do's row): the audit, 31 Oct,
  // Space on a focused block ran the timer
  return (key === " " || key === "Enter") && (target instanceof HTMLButtonElement || target.closest("[role=button]") !== null)
}

/** Whether something is open over the page that takes the keys: setup, a dialog. */
function modal(): boolean {
  return typeof document !== "undefined" && document.querySelector("[aria-modal=true]") !== null
}

export function useKeys(handlers: Partial<Record<KeyAction, () => void>>): void {
  const current = useRef(handlers)
  current.current = handlers
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      const action = keyAction({ key: e.key, meta: e.metaKey || e.ctrlKey, alt: e.altKey, busy: busy(e.target, e.key), modal: modal() })
      const handler = action && current.current[action]
      if (!handler) return
      e.preventDefault()
      handler()
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [])
}
