// The Mac app's menus and hotkeys (COMBINED.md 5, Mac/Sources/HostAction.swift): each arrives as a `friday:host`
// event, so the Mac app and the page share one implementation of every action. A browser never sends one.

import { useEffect, useRef } from "react"
import { fromMin } from "@/lib/time"
import { monthStart } from "@/plan/MonthView"
import type { CalendarPlace } from "./ShellContext"

export type HostName =
  | "newEvent"
  | "newTodo"
  | "search"
  | "ask"
  | "today"
  | "previous"
  | "next"
  | "view"
  | "drawer"
  | "go"
  | "ways"
  | "shove"
  | "pace"
  | "brief"
  | "tour"
  | "setup"
  | "triage"

export interface HostRequest {
  action: HostName
  argument?: string
}

const NAMES = new Set<string>(["newEvent", "newTodo", "search", "ask", "today", "previous", "next", "view", "drawer", "go", "ways", "shove", "pace", "brief", "triage", "tour", "setup"])
const PAGES = ["/", "/todo", "/projects", "/review", "/inbox", "/insights", "/rules", "/settings"]

/** The request in an event's detail, or null for anything Friday doesn't know. */
export function readHost(detail: unknown): HostRequest | null {
  if (typeof detail !== "object" || detail === null) return null
  const { action: name, argument } = detail as Record<string, unknown>
  if (typeof name !== "string" || !NAMES.has(name)) return null
  const action = name as HostName
  if (argument !== undefined && typeof argument !== "string") return null
  if (action === "view" && !["day", "three", "week", "month"].includes(argument ?? "")) return null
  if (action === "go" && !PAGES.some((p) => argument === p || (p !== "/" && argument?.startsWith(`${p}/`)))) return null
  return argument === undefined ? { action } : { action, argument }
}

export function shiftMonth(first: string, by: number): string {
  const y = Number(first.slice(0, 4))
  const m = Number(first.slice(5, 7)) - 1 + by
  return new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10)
}

/** Where the calendar goes for today, previous, next or a view; null when the request doesn't move it. */
export function placeAfter(request: HostRequest, place: CalendarPlace, today: string): CalendarPlace | null {
  const shown = place.first ?? (place.view === "month" ? monthStart(today) : today)
  const step = (by: number) => ({
    view: place.view,
    first: place.view === "month" ? shiftMonth(shown, by) : addDaysTo(shown, by * place.view),
  })
  switch (request.action) {
    case "today":
      return { view: place.view, first: null }
    case "previous":
      return step(-1)
    case "next":
      return step(1)
    case "view": {
      const view = request.argument === "day" ? 1 : request.argument === "three" ? 3 : request.argument === "week" ? 7 : "month"
      return { view, first: view === "month" ? monthStart(shown) : place.first }
    }
    default:
      return null
  }
}

function addDaysTo(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** A new event from the menu starts on the next whole hour, as a double-click on that hour would. */
export function nextHour(nowMinutes: number): string {
  return fromMin(Math.floor(nowMinutes / 60) * 60 + 60)
}

export function useHost(handle: (request: HostRequest) => void): void {
  const current = useRef(handle)
  current.current = handle
  useEffect(() => {
    const listen = (e: Event) => {
      const request = readHost((e as CustomEvent).detail)
      if (request) current.current(request)
    }
    window.addEventListener("friday:host", listen)
    return () => window.removeEventListener("friday:host", listen)
  }, [])
}
