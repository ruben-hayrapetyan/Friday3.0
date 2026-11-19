// Dragging across days to make them a break (19 Nov, you, of the prototype: "i like the dragging"): press on a day in
// the week's headers, the month or the sidebar's month, move to another and let go; the days between light up, and
// an offer opens where you let go: "Make these days a break…" (the break's popup, its dates filled in) or "Take them
// off" (an Off break at once, with Undo). A press without moving to another day is a click, as before.
//
// One drag at a time, shared by every place a day is drawn: a small store, read with useSyncExternalStore. Moves are
// followed on the document (elementFromPoint), so a touch, which keeps its events on the element it began on, works too.

import { useEffect, useRef, useSyncExternalStore } from "react"
import { useCommand } from "@/hooks/useCommand"
import { useMenuClose } from "@/components/fr/controls"
import { useShell } from "@/shell/ShellContext"
import { rangeWords } from "./words"

export type Span = { from: string; to: string }
type State = { active: boolean; span: Span | null; offer: { span: Span; x: number; y: number } | null }

let state: State = { active: false, span: null, offer: null }
const listeners = new Set<() => void>()
const set = (next: Partial<State>) => {
  state = { ...state, ...next }
  for (const l of listeners) l()
}
const subscribe = (l: () => void) => (listeners.add(l), () => listeners.delete(l))

/** The days a drag covers, first to last, whichever way it went. */
export function ordered(span: Span): Span {
  return span.from <= span.to ? span : { from: span.to, to: span.from }
}

/** Whether `date` is inside the span being dragged (or just offered). */
export function inSpan(span: Span | null, date: string): boolean {
  if (!span) return false
  const { from, to } = ordered(span)
  return date >= from && date <= to
}

/** The span lit up now: the drag going on, or the one its offer is about. */
export function useSpan(): Span | null {
  return useSyncExternalStore(subscribe, () => (state.active && state.span && state.span.from !== state.span.to ? state.span : state.offer?.span ?? null))
}

const dayAt = (x: number, y: number): string | null =>
  (document.elementFromPoint?.(x, y) as HTMLElement | null)?.closest<HTMLElement>("[data-span-day]")?.dataset.spanDay ?? null

let swallowClick = false // the click that ends a drag across days isn't a click on the last day

function move(e: PointerEvent) {
  if (!state.active || !state.span) return
  const day = dayAt(e.clientX, e.clientY)
  if (day && day !== state.span.to) set({ span: { ...state.span, to: day } })
}

// While days are dragged across, no text is selected (19 Nov, you, of 0.6.0: "when you select days for a break, it
// also selects all of the text on the page"; Safari's engine, the Mac app's, starts a selection over the page from a
// press it can't select in): none starts, and one begun is let go of.
const noSelecting = (e: Event) => e.preventDefault()

function holdSelection(on: boolean) {
  if (on) {
    window.getSelection?.()?.removeAllRanges()
    document.addEventListener("selectstart", noSelecting, true)
  } else {
    document.removeEventListener("selectstart", noSelecting, true)
  }
  document.documentElement.classList.toggle("fr-spanning", on)
}

function stopFollowing() {
  document.removeEventListener("pointermove", move)
  document.removeEventListener("pointerup", up)
  document.removeEventListener("pointercancel", cancel)
  window.removeEventListener("blur", cancel)
  holdSelection(false)
}

/** A drag that ends without letting go on a day (a touch the system took back, the window left mid-drag): nothing
 * offered, and the page selects again. */
function cancel() {
  stopFollowing()
  set({ active: false, span: null })
}

function up(e: PointerEvent) {
  stopFollowing()
  if (!state.active || !state.span) return
  const day = dayAt(e.clientX, e.clientY) ?? state.span.to
  const span = ordered({ from: state.span.from, to: day })
  if (span.from === span.to) return set({ active: false, span: null }) // a click: the day does what it always did
  swallowClick = true
  setTimeout(() => (swallowClick = false), 0)
  set({ active: false, span: null, offer: { span, x: e.clientX, y: e.clientY } })
}

/** What a day needs to be dragged across: put on the element that draws it. */
export function spanDay(date: string) {
  return {
    "data-span-day": date,
    onPointerDown: (e: React.PointerEvent) => {
      if ((e.button ?? 0) > 0 || (e.target as HTMLElement).closest("[data-no-span]")) return // the main button or a touch
      set({ active: true, span: { from: date, to: date }, offer: null })
      holdSelection(true)
      document.addEventListener("pointermove", move)
      document.addEventListener("pointerup", up)
      document.addEventListener("pointercancel", cancel)
      window.addEventListener("blur", cancel)
    },
    // the press itself starts no selection (a click still comes: it opens the day, as before)
    onMouseDown: (e: React.MouseEvent) => {
      if (e.button === 0 && !(e.target as HTMLElement).closest("[data-no-span]")) e.preventDefault()
    },
    onClickCapture: (e: React.MouseEvent) => {
      if (swallowClick) (e.stopPropagation(), e.preventDefault(), (swallowClick = false))
    },
  }
}

/** The offer where a drag across days ended: make them a break (its popup, dates filled in), or take them off. */
export function SpanOffer() {
  const offer = useSyncExternalStore(subscribe, () => state.offer)
  const { setBreakEdit } = useShell()
  const add = useCommand("vacation_add", { label: (o) => o.result.message })
  const box = useRef<HTMLDivElement>(null)
  const first = useRef<HTMLButtonElement>(null)
  const close = () => set({ offer: null })
  const escape = useMenuClose(!!offer, (open) => !open && close(), box, first)
  useEffect(() => {
    if (offer) first.current?.focus()
  }, [offer])
  if (!offer) return null
  const { span } = offer
  const left = Math.min(offer.x, window.innerWidth - 260)
  const top = Math.min(offer.y + 8, window.innerHeight - 140)
  return (
    <div ref={box} className="fr-float fr-menu-list" role="menu" aria-label="These days" onKeyDown={escape} style={{ position: "fixed", left: Math.max(8, left), top, zIndex: 60, width: 250 }}>
      <span className="fr-kicker" style={{ padding: "4px 10px 2px" }}>
        {rangeWords(span.from, span.to)}
      </span>
      <button ref={first} role="menuitem" onClick={() => (close(), setBreakEdit({ start: span.from, end: span.to }))}>
        <span>Make these days a break…</span>
      </button>
      <button role="menuitem" onClick={() => (close(), void add({ name: "Days off", start: span.from, end: span.to, mode: "off" }))}>
        <span>Take them off</span>
      </button>
    </div>
  )
}

/** For tests: no drag going on, nothing offered. */
export const forgetSpan = () => (stopFollowing(), set({ active: false, span: null, offer: null }))
