// Live updates over SSE (DESIGN §18.2). Each server event refreshes the queries it affects. A change's quick
// placement comes with the plan query itself until the solver's plan replaces it; ghosts are what Other ways lays
// over the calendar.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import type { Block } from "./client"

export const GHOSTS = ["ghosts"] as const

const EVERYTHING = "*"
const REFRESH: Record<string, string[]> = {
  // Every command sends it, and any query may read what a command changed (rules, tokens, calendars, mail…), so a
  // list kept by hand here went stale whenever a page was added.
  "items.changed": [EVERYTHING],
  "plan.changed": ["plan", "now", "items", "item", "calendar", "status", "why", "review", "projects", "exams", "load", "triage", "brief", "week"],
  "status.changed": ["status", "notifications", "questions"],
}

/** The query keys (by their first part) an event makes stale; "*" is all of them. */
export function refreshFor(event: string): string[] {
  return REFRESH[event] ?? []
}

export function setGhosts(client: QueryClient, ghosts: Block[]): void {
  client.setQueryData(GHOSTS, ghosts)
}

function refresh(client: QueryClient, event: string): void {
  const stale = refreshFor(event)
  // Ghosts are put there by hand (Other ways' preview): refetching them would only empty them.
  client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== GHOSTS[0] && (stale.includes(EVERYTHING) || stale.includes(String(q.queryKey[0]))) })
}

export function useServerEvents(): void {
  const client = useQueryClient()
  useEffect(() => {
    const source = new EventSource("/events")
    let dropped = false
    source.onerror = () => {
      dropped = true
    }
    source.onopen = () => {
      // Events sent while the stream was down are lost, so refresh everything once it is back.
      if (dropped) client.invalidateQueries()
      dropped = false
    }
    for (const event of Object.keys(REFRESH)) {
      source.addEventListener(event, () => {
        if (event === "plan.changed") setGhosts(client, [])
        refresh(client, event)
      })
    }
    return () => source.close()
  }, [client])
}
