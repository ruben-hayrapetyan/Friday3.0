// Several things on the calendar at once (27 Oct: "make the group select feature apply to all individual
// components"): ⌘-click (or Ctrl, or Shift) a block or an event to pick it along with the others, as the to-do list
// picks tasks. Dragging one picked block moves all of them by as much (days too), and the bar under the calendar
// (PickBar) does to all of them what a block's card does to one. A plain click, Esc or leaving the page lets go.

import { useSyncExternalStore } from "react"
import type { Block, Item } from "@/api/client"
import { fromMin, toMin } from "@/lib/time"

export interface Pick {
  key: string // the block's or `F` + the event's id, as the calendar draws it
  itemId: number
  title: string
  start: string
  end: string
  event: boolean
  pinned?: Block["pinned"]
}

let picked: Pick[] = []
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

export const picks = {
  get: (): Pick[] => picked,
  set(next: Pick[]): void {
    picked = next
    emit()
  },
  /** Pick it, or let it go if it was picked. The first ⌘-click also picks what was selected before, as the to-do
   * list does. */
  toggle(pick: Pick, selected: Pick | null): void {
    const from = picked.length || !selected || selected.key === pick.key ? picked : [selected]
    picks.set(from.some((p) => p.key === pick.key) ? from.filter((p) => p.key !== pick.key) : [...from, pick])
  },
  clear(): void {
    if (picked.length) picks.set([])
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

export const usePicks = (): Pick[] => useSyncExternalStore(picks.subscribe, picks.get)

export function pickOfBlock(b: Block): Pick {
  return { key: b.key, itemId: b.item_id, title: b.title, start: b.start, end: b.end, event: false, pinned: b.pinned }
}

export function pickOfEvent(e: Item & { start: string; end: string }): Pick {
  return { key: `F${e.id}`, itemId: e.id, title: e.title, start: e.start, end: e.end, event: true }
}

/** Where each picked thing goes when one of them is dragged `by` minutes, each keeping its length; a block's key
 * names its start, so it gets the key the plan will give it there. In the order the moves are made: the furthest
 * along first, so no block's new pin lands on one not moved yet and replaces it (commands/pins.py). */
export function shifted(list: Pick[], by: number): (Pick & { from: Pick })[] {
  const order = [...list].sort((a, b) => (by > 0 ? b.start.localeCompare(a.start) : a.start.localeCompare(b.start)))
  return order.map((p) => {
    const start = fromMin(toMin(p.start) + by)
    const end = fromMin(toMin(p.end) + by)
    return { ...p, start, end, key: p.event ? p.key : `T${p.itemId}@${start}`, from: p }
  })
}

/** To-do rows dropped together on the calendar: one after another from `start` (a minute), each for what's left of
 * it, in the order they're listed. */
export function inARow(rows: { id: number; title: string; length: number }[], start: number): Pick[] {
  let at = start
  return rows.map((r) => {
    const from = at
    at += r.length
    return { key: `R${r.id}`, itemId: r.id, title: r.title, start: fromMin(from), end: fromMin(at), event: false }
  })
}

/** The picks as the calendar has them now: an event at its time now, a block still where it was picked or moved to,
 * or the block of that task the plan joined it into (more of it planned just before). One the plan put elsewhere
 * (dropped on a class, say) is let go: there's nothing there to act on. The same list when
 * nothing changed, so a plan that changes nothing picked redraws nothing. */
export function current(list: Pick[], blocks: Block[], fixed: Item[]): Pick[] {
  const keys = new Map(blocks.map((b) => [b.key, b]))
  const events = new Map(fixed.map((f) => [f.id, f]))
  const now = list.flatMap((p): Pick[] => {
    const event = p.event ? events.get(p.itemId) : undefined
    if (event?.start && event.end) return [{ ...p, start: event.start, end: event.end }]
    const block = p.event ? undefined : keys.get(p.key) ?? blocks.find((b) => b.item_id === p.itemId && b.start <= p.start && p.end <= b.end)
    return block ? [{ ...p, key: block.key, start: block.start, end: block.end, pinned: block.pinned }] : []
  })
  const same = now.length === list.length && now.every((p, n) => p.key === list[n].key && p.start === list[n].start && p.end === list[n].end && (p.pinned ?? null) === (list[n].pinned ?? null))
  return same ? list : now
}

/** The items behind the picks, once each: two blocks of one task are one task to mark done or give a due. */
export function itemsOf(list: Pick[], blocksOnly = false): number[] {
  return [...new Set(list.filter((p) => !blocksOnly || !p.event).map((p) => p.itemId))]
}
