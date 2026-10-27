// The same shortcut again takes back what it opened (27 Oct: "make the same keyboard command done again undo the
// action, eg option space gets rid of the popup, cmd k get rid of the popup"): ⌥Space or ⌘N a new event, ⌘K or ⌘F
// search, ⌘J or ⌃Space Ask Claude, S Shove, P Pace. Only while Friday was already in front: the Mac's hotkeys also
// bring it up from behind other apps, and then they open what they open, whatever was left open before.

export type Opener = "search" | "ask" | "newEvent" | "shove" | "pace"

export interface Opened {
  dialog: string | null
  pop: string | null
  newEvent: boolean // the drawer holds a new event, not yet saved
}

/** Whether what a shortcut opens is open now. */
export function isOpen(opener: Opener, open: Opened): boolean {
  switch (opener) {
    case "search":
    case "ask":
      return open.dialog === opener
    case "newEvent":
      return open.newEvent
    case "shove":
    case "pace":
      return open.pop === opener
  }
}

/** Whether a shortcut closes what it opened rather than opening it. */
export function closes(opener: Opener, open: Opened, inFront: boolean): boolean {
  return inFront && isOpen(opener, open)
}

// When Friday last came to the front: a hotkey that brought it up arrives within moments of it, and opens.
const SETTLE_MS = 400
let frontSince = typeof document !== "undefined" && document.hasFocus() ? 0 : Number.POSITIVE_INFINITY

if (typeof window !== "undefined") {
  window.addEventListener("focus", () => (frontSince = Date.now()))
  window.addEventListener("blur", () => (frontSince = Number.POSITIVE_INFINITY))
}

/** Whether Friday was in front before this key: focused, and not just now brought up. */
export function wasInFront(now = Date.now(), since = frontSince, focused = typeof document !== "undefined" && document.hasFocus()): boolean {
  return focused && now - since > SETTLE_MS
}
