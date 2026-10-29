// Drag on pointer events, no library (DESIGN §18.4). One drag at a time, shared by the calendar and the to-do pane:
// day columns carry `data-top-min` (the minute at their top), the pane `data-drop="todo"`, and whole days (month
// cells, the mini month, day headers) `data-drop-day` with their date: a task dropped there is due that day
// (COMBINED.md 16).

import { createContext, type ReactNode, useCallback, useContext, useRef, useState } from "react"
import { type DragStart, dragged } from "@/lib/drag"
import { ROW_MIN } from "@/lib/time"
import { PX as PX_PER_MIN } from "@/plan/Pieces"

export interface Drag extends DragStart {
  itemId: number | null // null for a selection of empty time
  blockKey: string | null
  title: string
  locked: boolean // Shift held: pin as locked
  at: { start: number; end: number } | null // where it would land in the calendar
  over: "calendar" | "todo" | "day" | null
  day: string | null // the date of the day it's over
  moved: boolean
  x: number
  y: number
  group?: boolean // a picked block, carrying the others picked with it (plan/picks.ts)
  rows?: Row[] // to-do rows picked together in the drawer, planned one after another where they're dropped
  event?: boolean // an event's edge (29 Oct): its new time is saved as typing it over the event saves it
}

export interface Row {
  id: number
  title: string
  length: number // minutes
}

export type DropHandler = (drag: Drag) => void

interface DragApi {
  drag: Drag | null
  begin: (e: React.PointerEvent, from: Omit<Drag, "at" | "over" | "day" | "moved" | "locked" | "x" | "y">) => void
}

const DragContext = createContext<DragApi>({ drag: null, begin: () => {} })

export const useDragging = () => useContext(DragContext)

/** The calendar minute under the pointer, "todo", a whole day, or nothing. */
export function pointAt(x: number, y: number): number | "todo" | { day: string } | null {
  for (const el of document.elementsFromPoint(x, y)) {
    if (!(el instanceof HTMLElement)) continue
    if (el.dataset.drop === "todo") return "todo"
    if (el.dataset.dropDay) return { day: el.dataset.dropDay }
    if (el.dataset.topMin) return Number(el.dataset.topMin) + (y - el.getBoundingClientRect().top) / PX_PER_MIN
  }
  return null
}

/** The calendar minute under a pointer event. */
export function minuteAt(e: React.PointerEvent): number {
  const found = pointAt(e.clientX, e.clientY)
  return typeof found === "number" ? found : 0
}

// A click follows the pointerup that ends a short drag inside a block; it shouldn't also open the drawer.
let draggedAt = 0
export const justDragged = () => Date.now() - draggedAt < 300

export function DragProvider({ onDrop, children }: { onDrop: DropHandler; children: ReactNode }) {
  const [drag, setDrag] = useState<Drag | null>(null)
  const current = useRef<Drag | null>(null)
  const show = (next: Drag | null) => {
    current.current = next
    setDrag(next)
  }
  const begin = useCallback<DragApi["begin"]>(
    (e, from) => {
      if (e.button !== 0) return
      e.preventDefault()
      const origin = { x: e.clientX, y: e.clientY }
      show({ ...from, at: null, over: null, day: null, moved: false, locked: e.shiftKey, x: e.clientX, y: e.clientY })
      const move = (ev: PointerEvent) => {
        const was = current.current
        if (!was) return
        const point = pointAt(ev.clientX, ev.clientY)
        show({
          ...was,
          moved: was.moved || Math.hypot(ev.clientX - origin.x, ev.clientY - origin.y) > 4,
          locked: ev.shiftKey,
          over: point === "todo" ? "todo" : point === null ? null : typeof point === "object" ? "day" : "calendar",
          day: point !== null && typeof point === "object" ? point.day : null,
          at: typeof point === "number" ? dragged(was, point) : null,
          x: ev.clientX,
          y: ev.clientY,
        })
      }
      const up = () => {
        window.removeEventListener("pointermove", move)
        window.removeEventListener("pointerup", up)
        const done = current.current
        show(null)
        if (done?.moved) draggedAt = Date.now()
        if (done) onDrop(done)
      }
      window.addEventListener("pointermove", move)
      window.addEventListener("pointerup", up)
    },
    [onDrop],
  )
  return <DragContext.Provider value={{ drag, begin }}>{children}</DragContext.Provider>
}

export function selectionFrom(minute: number): DragStart {
  const start = Math.floor(minute / ROW_MIN) * ROW_MIN
  return { kind: "select", start, end: start + ROW_MIN, grab: 0 }
}
