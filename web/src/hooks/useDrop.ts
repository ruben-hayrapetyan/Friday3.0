// What a finished drag does (DESIGN §18.4): a block or a to-do row dropped on the calendar is pinned there
// (preferred, or locked with Shift); a block dropped on the to-do pane is unpinned; a selection opens its menu.
// Resizing a block pins it with its new length. Dropped on a whole day (a month cell, the mini month, a day's
// header) it is due that day instead, at the time it had or 23:59 (COMBINED.md 16, as personal's Deadlines.swift).

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import type { Block, Item } from "@/api/client"
import type { Drag } from "@/components/calendar/useDrag"
import { type Toast, useToast } from "@/components/Toasts"
import { weekday } from "@/lib/format"
import { fromMin } from "@/lib/time"
import { placedByHand } from "@/plan/glide"
import { pending } from "@/plan/pending"
import { runCommand } from "./useCommand"

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
      if (drag.kind === "resize") await lengthen(client, toast, drag.itemId, drag.at.end - drag.at.start - (drag.end - drag.start))
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
