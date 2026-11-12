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
  "status.changed": ["status", "questions"],
  // A change's quick placement, made after it answered (server/placer.py): the calendar draws it.
  "plan.provisional": ["plan"],
  // A downloaded Friday looked for a newer version (commands/updates.py): the popup and Settings → Updates.
  "updates.changed": ["updates"],
}

// What the commands you click most change (the server names the command with items.changed, server/app.py
// announce): the to-dos and what's read from them, not settings, rules, terms, meals or sleep. Any other command
// still refreshes everything; the plan's own queries come with plan.changed once it's planned again (12 Nov: a click
// had the page read some 35 things at once, and the next click waited behind them).
const WORK = ["items", "item", "status", "now", "calendar", "review", "week_review", "projects", "exams", "inbox", "to_review", "duplicates", "questions", "asks_later", "insights", "load", "triage", "brief", "why", "why_not", "rule_totals", "series_list", "log_list", "events", "changes"]
const BY_COMMAND: Record<string, string[]> = Object.fromEntries([
  ...["suggestion_accept", "suggestion_reject", "suggestion_restore", "batch_accept", "add", "edit", "done", "reopen", "drop", "start", "stop", "pin", "unpin", "skip", "settle", "depend", "undepend", "event_hold", "event_keep", "reorder", "progress", "log", "stuck", "sitting_edit", "sitting_delete", "review_task"].map((c) => [c, WORK]),
  ...["meal_start", "meal_end", "meal_skip", "meal_log", "meal_edit", "meal_remove"].map((c) => [c, [...WORK, "meals"]]),
  ...["sleep_mark", "sleep_mark_edit", "sleep_mark_remove", "nap_start", "nap_end"].map((c) => [c, [...WORK, "sleep"]]),
])

/** The query keys (by their first part) an event makes stale; "*" is all of them. `command`: the one that changed
 * things, for items.changed. */
export function refreshFor(event: string, command?: string): string[] {
  if (event === "items.changed" && command && BY_COMMAND[command]) return BY_COMMAND[command]
  return REFRESH[event] ?? []
}

export function setGhosts(client: QueryClient, ghosts: Block[]): void {
  client.setQueryData(GHOSTS, ghosts)
}

/** Whether the live stream is open: while it is, its events refresh what changed and a command needn't do it too. */
export let streamLive = false

// Events close together refresh once (12 Nov: a command's items.changed, then plan.changed, then its own refresh, each
// read the page's queries again): what they make stale is gathered for a moment, then read once.
const GATHER_MS = 120
const gathered = new Map<QueryClient, { keys: Set<string>; timer: ReturnType<typeof setTimeout> }>()

export function refresh(client: QueryClient, event: string, command?: string): void {
  staleSoon(client, refreshFor(event, command))
}

/** Marks these query families stale (EVERYTHING: all) once the moment's events are in. */
export function staleSoon(client: QueryClient, keys: string[]): void {
  const now = gathered.get(client)
  if (now) {
    for (const k of keys) now.keys.add(k)
    return
  }
  const pending = { keys: new Set(keys), timer: setTimeout(() => flush(client), GATHER_MS) }
  gathered.set(client, pending)
}

function flush(client: QueryClient): void {
  const pending = gathered.get(client)
  gathered.delete(client)
  if (!pending) return
  const all = pending.keys.has(EVERYTHING)
  // Ghosts are put there by hand (Other ways' preview): refetching them would only empty them.
  void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== GHOSTS[0] && (all || pending.keys.has(String(q.queryKey[0]))) })
}

/** Events sent while the stream wasn't open are lost: once it's back, refresh everything; the first time it opens,
 * whatever was asked before it opened (8 Nov: Friday's update, found a second after launch, never popped up). */
export function refreshMissed(client: QueryClient, dropped: boolean, opened: number): void {
  if (dropped) {
    void client.invalidateQueries()
    return
  }
  void client.invalidateQueries({
    predicate: (q) => q.queryKey[0] !== GHOSTS[0] && (q.state.fetchStatus === "fetching" || q.state.dataUpdatedAt < opened),
  })
}

export function useServerEvents(): void {
  const client = useQueryClient()
  useEffect(() => {
    const source = new EventSource("/events")
    let dropped = false
    source.onerror = () => {
      dropped = true
      streamLive = false
    }
    source.onopen = () => {
      refreshMissed(client, dropped, Date.now())
      dropped = false
      streamLive = true
    }
    for (const event of Object.keys(REFRESH)) {
      source.addEventListener(event, (e) => {
        if (event === "plan.changed") setGhosts(client, [])
        let command: string | undefined
        try {
          command = (JSON.parse((e as MessageEvent).data ?? "{}") as { command?: string }).command
        } catch {
          command = undefined
        }
        refresh(client, event, command)
      })
    }
    return () => {
      streamLive = false
      source.close()
    }
  }, [client])
}
