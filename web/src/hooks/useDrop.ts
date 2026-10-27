// What a finished drag does (DESIGN §18.4): a block or a to-do row dropped on the calendar is pinned there
// (preferred, or locked with Shift); a block dropped on the to-do pane is unpinned; a selection opens its menu.
// Resizing a block pins it with its new length. Dropped on a whole day (a month cell, the mini month, a day's
// header) it is due that day instead, at the time it had or 23:59 (COMBINED.md 16, as personal's Deadlines.swift).
// A block picked with others (plan/picks.ts) takes them along: all move by as much, all are due that day, or all go
// back to Friday.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import type { Block, Item } from "@/api/client"
import type { Drag } from "@/components/calendar/useDrag"
import { type Toast, useToast } from "@/components/Toasts"
import { weekday } from "@/lib/format"
import { fromMin } from "@/lib/time"
import { placedByHand } from "@/plan/glide"
import { pending } from "@/plan/pending"
import { inARow, itemsOf, type Pick, picks, shifted } from "@/plan/picks"
import { rememberTogether, runCommand, undoAll } from "./useCommand"

export interface Selection {
  start: string
  end: string
  x: number
  y: number
}

/** Show a pinned block where it was dropped until a plan has the pin (plan/pending.ts). */
export function moveBlock(_client: QueryClient, key: string, start: string, end: string, kind: Block["pinned"]): void {
  const item = /^T(\d+)@/.exec(key)
  if (item) placedByHand(Number(item[1])) // it's where you let go: it doesn't slide there (plan/glide.ts)
  pending.add((plan) => ({
    ...plan,
    // The key names the start, so the moved block gets a new one and stays selectable by it.
    blocks: plan.blocks.map((b) => (b.key === key ? { ...b, key: `T${b.item_id}@${start}`, start, end, pinned: kind } : b)),
  }))
}

/** Show an event you added or retimed in the drawer where you put it until the server's plan arrives: a new one
 * appeared only when the calendar refreshed, after the drawer had closed (27 Oct). */
export function placeEvent(_client: QueryClient, given: object | null): void {
  const input = (given ?? {}) as Record<string, unknown>
  const { id, start, end } = input
  if (typeof start !== "string" || typeof end !== "string" || (id === undefined && input.when !== "fixed")) return
  const fields = Object.fromEntries(["title", "start", "end", "color", "notes", "blocks_time"].filter((k) => input[k] !== undefined).map((k) => [k, input[k]]))
  const made = { ...NEW_EVENT, id: -Date.now(), ...fields } as unknown as Item
  pending.add((plan) => {
    if (typeof id === "number") return { ...plan, fixed: plan.fixed.map((f) => (f.id === id ? { ...f, ...fields } : f)) }
    // Until the plan has the event itself: then it's there twice for a moment, so the stand-in steps aside.
    if (plan.fixed.some((f) => f.title === made.title && f.start === made.start && f.end === made.end)) return plan
    return { ...plan, fixed: [...plan.fixed, made] }
  })
}

const NEW_EVENT = { preset: "Event", area: null, tags: [], when: "fixed", status: "todo", event_kind: "other", blocks_time: true, notes: "" }

/** The due a task gets when dropped on a day: that day at the time it was due, or 23:59. */
export function dueOn(day: string, was: string | null | undefined): string {
  return `${day}T${was && was.length >= 16 ? was.slice(11, 16) : "23:59"}`
}

function knownDue(client: QueryClient, id: number): string | null | undefined {
  for (const [, items] of client.getQueriesData<Item[]>({ queryKey: ["items"] })) {
    const found = Array.isArray(items) ? items.find((i) => i.id === id) : undefined
    if (found) return found.due
  }
  return undefined
}

/** A resized block of a fixed-length item changes the item's length too, by as much as the block grew. */
async function lengthen(client: QueryClient, toast: (t: Toast) => void, id: number, by: number): Promise<void> {
  const item = client.getQueryData<Item[]>(["items"])?.find((i) => i.id === id)
  if (!by || item?.amount !== "fixed" || item.duration_min == null) return
  await runCommand(client, toast, "edit", { id, duration_min: Math.max(15, item.duration_min + by) })
}

// Moves are sent one after another, in the order they were made (27 Oct: two quick presses of ↓ sent their pins at
// once; the second, answered first, was then replaced by the first's, and the block stayed a quarter hour short).
let moving: Promise<unknown> = Promise.resolve()

/** `run` once every move made before it has been answered. */
export function inOrder<T>(run: () => Promise<T>): Promise<T> {
  const next = moving.then(run, run)
  moving = next.catch(() => undefined)
  return next
}

/** Every picked block and event moved `by` minutes together: a block pinned where it lands, as dragging it pins it
 * (locked if it was, or with Shift), an event retimed as typing its time does. All of them move on the calendar at
 * once; the changes are then made one by one, in an order where no new pin replaces a block not moved yet, and come
 * back as one change with one Undo. The picks follow, so they can be moved again. */
export async function moveGroup(client: QueryClient, toast: (t: Toast) => void, list: Pick[], by: number, locked = false): Promise<void> {
  if (!by || !list.length) return
  const moved = shifted(list, by).map((p) => ({ ...p, pinned: p.event ? undefined : locked || p.pinned === "locked" ? ("locked" as const) : ("preferred" as const) }))
  picks.set(moved.map(({ from: _, ...p }) => p))
  const drawn = moved.map((p) =>
    pending.collect(() => (p.event ? placeEvent(client, { id: p.itemId, start: p.start, end: p.end }) : moveBlock(client, p.from.key, p.start, p.end, p.pinned ?? "preferred"))),
  )
  return inOrder(() => sendMoves(client, toast, moved, drawn, list.length, by))
}

async function sendMoves(client: QueryClient, toast: (t: Toast) => void, moved: (Pick & { from: Pick })[], drawn: number[][], count: number, by: number): Promise<void> {
  const ids: number[] = []
  for (const [n, p] of moved.entries()) {
    const out = p.event
      ? await runCommand(client, toast, "edit", { id: p.itemId, start: p.start, end: p.end }, { quiet: true })
      : await runCommand(client, toast, "pin", { id: p.itemId, start: p.start, end: p.end, kind: p.pinned ?? "preferred", from_start: p.from.start, from_end: p.from.end }, { quiet: true })
    if (!out) {
      drawn.slice(n).forEach((d) => pending.drop(d)) // that one failed and said why: the rest stay where they are
      break
    }
    pending.settle(drawn[n], (out as { generation?: number | null }).generation ?? 0)
    if (out.command_id != null) ids.push(out.command_id)
  }
  rememberTogether(ids)
  if (ids.length) toast({ message: `Moved ${count} ${by < 0 ? "earlier" : "later"}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
}

/** The picked blocks' tasks each due on `day`, or each left to Friday again (their pins taken off). */
async function groupTo(client: QueryClient, toast: (t: Toast) => void, list: Pick[], day: string | null): Promise<void> {
  const ids: number[] = []
  const tasks = itemsOf(day ? list : list.filter((p) => p.pinned), true)
  for (const id of tasks) {
    const out = day
      ? await runCommand(client, toast, "edit", { id, due: dueOn(day, knownDue(client, id)) }, { quiet: true })
      : await runCommand(client, toast, "unpin", { id }, { quiet: true })
    if (out?.command_id != null) ids.push(out.command_id)
  }
  rememberTogether(ids)
  const said = day ? `${tasks.length} due ${weekday(day)} ${Number(day.slice(8, 10))}` : `Friday decides ${tasks.length} again`
  if (ids.length) toast({ message: `${said}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
  if (!day) picks.clear()
}

/** To-do rows picked together in the drawer and dropped: on a day, all due that day; on the calendar, pinned one
 * after another from where they were let go. */
async function dropRows(client: QueryClient, toast: (t: Toast) => void, drag: Drag): Promise<void> {
  const rows = drag.rows ?? []
  const day = drag.over === "day" ? drag.day : null
  if (!day && !(drag.over === "calendar" && drag.at)) return
  const kind = drag.locked ? "locked" : "preferred"
  const placed = drag.at ? inARow(rows, drag.at.start) : []
  const ids: number[] = []
  for (const [n, r] of rows.entries()) {
    const out = day
      ? await runCommand(client, toast, "edit", { id: r.id, due: dueOn(day, knownDue(client, r.id)) }, { quiet: true })
      : await runCommand(client, toast, "pin", { id: r.id, start: placed[n].start, end: placed[n].end, kind }, { quiet: true })
    if (out?.command_id != null) ids.push(out.command_id)
  }
  rememberTogether(ids)
  const said = day ? `${rows.length} due ${weekday(day)} ${Number(day.slice(8, 10))}` : `Planned ${rows.length} one after another`
  if (ids.length) toast({ message: `${said}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
}

export function useDrop(onSelection: (selection: Selection) => void): (drag: Drag) => void {
  const client = useQueryClient()
  const toast = useToast()
  return useCallback(
    async (drag: Drag) => {
      if (!drag.moved) return
      if (drag.kind === "select") {
        if (drag.at) onSelection({ start: fromMin(drag.at.start), end: fromMin(drag.at.end), x: drag.x, y: drag.y })
        return
      }
      if (drag.itemId === null) return
      if (drag.rows && drag.rows.length > 1) return void dropRows(client, toast, drag)
      if (drag.group && drag.kind === "move") {
        const list = picks.get()
        if (drag.over === "day" && drag.day) return void groupTo(client, toast, list, drag.day)
        if (drag.over === "todo") return void groupTo(client, toast, list, null)
        if (drag.over === "calendar" && drag.at) return void moveGroup(client, toast, list, drag.at.start - drag.start, drag.locked)
        return
      }
      if (drag.over === "day" && drag.day) {
        const due = dueOn(drag.day, knownDue(client, drag.itemId))
        const day = drag.day
        runCommand(client, toast, "edit", { id: drag.itemId, due }, { label: () => `${drag.title} is due ${weekday(day)} ${Number(day.slice(8, 10))}` })
        return
      }
      if (drag.over === "todo" && drag.kind !== "row") {
        runCommand(client, toast, "unpin", { id: drag.itemId })
        return
      }
      if (drag.over !== "calendar" || !drag.at) return
      const start = fromMin(drag.at.start)
      const end = fromMin(drag.at.end)
      const kind = drag.locked ? "locked" : "preferred"
      const key = drag.blockKey
      if (drag.kind === "resize" || drag.kind === "resize-top") await lengthen(client, toast, drag.itemId, drag.at.end - drag.at.start - (drag.end - drag.start))
      runCommand(
        client,
        toast,
        "pin",
        // A row keeps the server's length (what's left of the item); a block keeps what was dragged, and its pin
        // replaces the one where it was.
        drag.kind === "row"
          ? { id: drag.itemId, start, kind }
          : { id: drag.itemId, start, end, kind, from_start: fromMin(drag.start), from_end: fromMin(drag.end) },
        { optimistic: key ? (c) => moveBlock(c, key, start, end, kind) : undefined },
      )
    },
    [client, toast, onSelection],
  )
}
