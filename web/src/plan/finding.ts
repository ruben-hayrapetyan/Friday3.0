// Finding other ways to plan the week, as a dialogue (6 Nov: "it just says the same static thing for over 20
// seconds"; the CS 2112 UI lecture: show progress of longer actions, short interactions with clear progress, and past
// ten seconds let the user do something else). Each way is about half a minute of planning on a full term, so they
// are asked for one at a time and each card shows as it comes; the one being planned counts its seconds against how
// long the last took; you can close the window and keep working, and Friday says when they're ready. The rules are
// pure functions here; the one search in flight is kept below.

import { useSyncExternalStore } from "react"
import { query, type Schemas } from "@/api/client"

type Way = Schemas["OtherWay"]

export interface Finding {
  id: number
  began: number // ms, the search
  wayBegan: number // ms, the way being planned now
  tried: number // seeds asked about so far
  tries: number // at most
  wanted: number
  ways: Way[]
  state: "planning" | "done" | "stopped" | "failed"
  lastMs: number | null // how long one way took, last time: what the bar fills against
  error?: string
}

export const begin = (id: number, now: number, lastMs: number | null): Finding => ({
  id,
  began: now,
  wayBegan: now,
  tried: 0,
  tries: 6,
  wanted: 2,
  ways: [],
  state: "planning",
  lastMs,
})

/** One seed's answer: its way kept unless it's one already found; done with enough ways or no seeds left. */
export function found(was: Finding, way: Way | null, tries: number, wanted: number, now: number): Finding {
  if (was.state !== "planning") return was
  const fresh = way && !was.ways.some((w) => w.signature === way.signature) ? [way] : []
  const ways = [...was.ways, ...fresh]
  const tried = was.tried + 1
  const done = ways.length >= wanted || tried >= tries
  return { ...was, ways, tried, tries, wanted, wayBegan: now, lastMs: now - was.wayBegan, state: done ? "done" : "planning" }
}

export const failed = (was: Finding, error: string): Finding => (was.state === "planning" ? { ...was, state: "failed", error } : was)
export const stopped = (was: Finding): Finding => (was.state === "planning" ? { ...was, state: "stopped" } : was)

const seconds = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`
}

export interface Slot {
  way?: Way
  line: string // what the slot is doing
  share: number | null // how far, 0–1, against how long the last way took; null when Friday can't say
}

/** Each of the ways wanted: found, being planned (with its seconds), or next. */
export function slots(f: Finding, now: number): Slot[] {
  return Array.from({ length: f.wanted }, (_, i): Slot => {
    if (f.ways[i]) return { way: f.ways[i], line: "", share: 1 }
    if (i > f.ways.length || f.state !== "planning") return { line: f.state === "planning" ? "Next" : "Not planned", share: null }
    const spent = now - f.wayBegan
    const again = f.tried > f.ways.length ? ", another try: the last came out like yours" : ""
    // Past how long the last way took, the bar moves rather than sitting nearly full: it can't say how much is left.
    const share = f.lastMs && spent < f.lastMs ? Math.min(0.95, spent / f.lastMs) : null
    return { line: `Planning way ${i + 1}… ${seconds(spent)}${again}`, share }
  })
}

/** The line under the title: what's happening, about how long, and once it's slow that you needn't wait. */
export function heading(f: Finding | null, now: number): { line: string; note: string | null } {
  if (!f || f.state === "planning") {
    const each = f?.lastMs ? `, about ${Math.max(5, Math.round(f.lastMs / 5000) * 5)}s each` : ""
    const spent = f ? now - f.began : 0
    return {
      line: `Planning your week two more ways${each}. ${f && f.ways.length ? `${f.ways.length} of ${f.wanted} ready` : "Each shows here as it's ready"}.`,
      note: spent >= 8000 ? "You can close this and keep working: Friday says when they're ready." : null,
    }
  }
  if (f.state === "failed") return { line: `Couldn't plan other ways: ${f.error}`, note: null }
  if (f.state === "stopped") return { line: f.ways.length ? "Stopped: the ways found so far." : "Stopped.", note: null }
  if (!f.ways.length) return { line: "Nothing much else would change: your plan is the way it fits.", note: null }
  const one = f.ways.length < f.wanted ? " Only one came out different from your plan." : ""
  return { line: `The same work, planned differently. Preview one on the calendar, or pick it.${one}`, note: null }
}

/** Ways found a while ago are planned again: your week has moved on since. */
export const FRESH_MS = 10 * 60_000
export const stale = (f: Finding | null, now: number) => !f || f.state === "failed" || (f.state !== "planning" && now - f.began > FRESH_MS)

// The one search in flight, shared by every Other ways window.
const LAST = "friday.wayMs"
let current: Finding | null = null
let controller: AbortController | null = null
let windowOpen = false
const listeners = new Set<() => void>()
const set = (next: Finding | null) => {
  current = next
  for (const l of listeners) l()
}
const saved = () => {
  const n = Number(globalThis.localStorage?.getItem(LAST))
  return Number.isFinite(n) && n > 0 ? n : null
}

export const finding = {
  get: () => current,
  /** Plan the ways, one seed at a time; `ready` runs when they're done while the window is closed. */
  async start(ready: (f: Finding) => void): Promise<void> {
    controller?.abort()
    const ctl = (controller = new AbortController())
    const id = Date.now() + Math.random()
    set(begin(id, Date.now(), saved()))
    for (let seed = 1; current?.id === id && current.state === "planning" && seed <= current.tries; seed++) {
      try {
        const out = await query("other_way", { seed }, ctl.signal)
        if (current?.id !== id) return
        set(found(current, out.way ?? null, out.tries, out.wanted, Date.now()))
        if (current.lastMs) globalThis.localStorage?.setItem(LAST, String(current.lastMs))
      } catch (error) {
        if (current?.id === id) set(failed(current, error instanceof Error ? error.message : String(error)))
        return
      }
    }
    if (current?.id === id && current.state === "done" && !windowOpen) ready(current)
  },
  stop() {
    controller?.abort()
    if (current) set(stopped(current))
  },
  open: (on: boolean) => (windowOpen = on),
}

export function useFinding(): Finding | null {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => current,
  )
}
