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
}

export function keyAction({ key, meta, alt, busy }: KeyPress): KeyAction | null {
  if (meta && (key.toLowerCase() === "k" || key.toLowerCase() === "f")) return "palette" // one search (COMBINED.md 57)
  if (busy || alt) return null
  if (meta) return key.toLowerCase() === "z" ? "undo" : null
  return SINGLE[key] ?? null
}

function busy(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target.closest("input, textarea, select, [role=dialog], [role=menu]")) return true
  return target instanceof HTMLButtonElement && (key === " " || key === "Enter") // they press the focused button
}

export function useKeys(handlers: Partial<Record<KeyAction, () => void>>): void {
  const current = useRef(handlers)
  current.current = handlers
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      const action = keyAction({ key: e.key, meta: e.metaKey || e.ctrlKey, alt: e.altKey, busy: busy(e.target, e.key) })
      const handler = action && current.current[action]
      if (!handler) return
      e.preventDefault()
      handler()
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [])
}
