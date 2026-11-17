// Every change goes through here (DESIGN §18.2): optimistic display, the command, ghosts, an Undo toast, and a
// rollback with the server's message on error. In What if, a change made on the Plan page is staged instead
// (`whatif/store.ts`): nothing is sent until you keep it.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { command, type CommandInput, type CommandName, errorWords, type Output } from "@/api/client"
import { refreshFor, staleSoon, streamLive } from "@/api/events"
import { type Toast, useToast } from "@/components/Toasts"
import { markedDone, mealEnded, mealSkipped, mealStarted, napEnded, napStarted, sleepMarked, timerStarted, timerStopped } from "@/now/instant"
import { pending } from "@/plan/pending"
import { whatIf } from "@/whatif/store"
import { expectPlan } from "@/lib/replan"

// settings too: a look flipped on the calendar goes back when the server refuses it (audit, 8 Nov); projects and
// exams, a tag picked on a project's page or an exam's card (15 Nov); ongoing and finished projects (projects-v2)
const OPTIMISTIC = ["items", "item", "plan", "now", "status", "meals", "sleep", "settings", "rules", "projects", "exams", "ongoing_projects", "projects_finished", "project_options"]

// What these change in the Now bar and the timer, shown before the server answers wherever they're made from: the
// bar, a block's card, a to-do, Space (now/instant.ts).
const INSTANT: Record<string, (client: QueryClient, input: never) => void> = {
  start: timerStarted,
  stop: timerStopped,
  done: markedDone,
  meal_start: mealStarted,
  meal_end: mealEnded,
  meal_skip: mealSkipped,
  sleep_mark: sleepMarked,
  nap_start: napStarted,
  nap_end: napEnded,
  settings_set: settingSet,
}

// Settings the server saves in part, keeping what the change doesn't name (commands/settings.py settings_set).
const SAVED_IN_PART = new Set(["event_kinds", "pace", "llm", "sleep"])

/** A setting shows changed at once, so a second click builds on the first rather than on the settings from before
 * either (the audit, 12 Nov: two quick clicks each wrote the whole list back, and the first was lost); refused, it goes
 * back with the rest. */
function settingSet(client: QueryClient, input: { key?: string; value?: unknown } | null): void {
  const key = input?.key
  if (!key) return
  client.setQueryData<Record<string, unknown>>(["settings"], (was) => {
    if (!was) return was
    const now = was[key]
    const value = input?.value
    const inPart = SAVED_IN_PART.has(key) && isObject(now) && isObject(value)
    return { ...was, [key]: inPart ? { ...now, ...value } : value }
  })
}

const isObject = (x: unknown): x is Record<string, unknown> => !!x && typeof x === "object" && !Array.isArray(x)

// Changes to one thing reach the server in the order you made them; changes to different things go at once (16 Nov:
// an ongoing project's hours set to 5h, then 4h, were both sent at once and saved as 5h when the first finished last).
const lanes = new Map<string, Promise<unknown>>()

/** For tests: no change waiting in any lane. */
export function clearLanes(): void {
  lanes.clear()
}

/** What a command changes, as far as order goes: its id, its setting's key or its block; none, no waiting. */
export function laneOf(input: unknown): string | null {
  if (!isObject(input)) return null
  if (typeof input.id === "number") return `id ${input.id}`
  if (typeof input.key === "string") return `key ${input.key}`
  if (typeof input.block_key === "string") return `block ${input.block_key}`
  return null
}

// A change answered by nothing (a server that stopped answering) holds the next only this long, not for ever.
const WAIT_MS = 10_000

/** `send`, once every earlier change in its lane has been answered (or refused), or after WAIT_MS. */
export function inTurn<T>(lane: string | null, send: () => Promise<T>): Promise<T> {
  if (lane === null) return send()
  const before = lanes.get(lane)
  const mine = before ? Promise.race([before, new Promise((wait) => setTimeout(wait, WAIT_MS))]).then(send) : send() // nothing ahead: sent now
  const settled = mine.catch(() => undefined)
  lanes.set(lane, settled)
  void settled.then(() => lanes.get(lane) === settled && lanes.delete(lane))
  return mine
}

// The newest change this page made, for ⌘Z: one command, or several made as one (a change to many to-dos).
let lastCommands: number[] = []

/** ⌘Z undoes these together, as the toast's Undo does. */
export function rememberTogether(ids: number[]): void {
  if (ids.length) lastCommands = ids
}

export interface Options<N extends CommandName> {
  optimistic?: (client: QueryClient, input: CommandInput<N>) => void
  label?: (out: Output<N>) => string
  quiet?: boolean // the caller says it worked itself (Shove's check), so no toast; ⌘Z still undoes it
}

export async function runCommand<N extends CommandName>(
  client: QueryClient,
  toast: (toast: Toast) => void,
  name: N,
  input: CommandInput<N>,
  { optimistic, label, quiet }: Options<N> = {},
): Promise<Output<N> | undefined> {
  if (whatIf.stages(name)) {
    whatIf.stage(name, input as Record<string, unknown>) // the header and the changes say so: no toast for each
    return { command_id: null, result: { message: "In What if" } } as unknown as Output<N>
  }
  const matches = { predicate: (q: { queryKey: readonly unknown[] }) => OPTIMISTIC.includes(String(q.queryKey[0])) }
  const saved = client.getQueriesData(matches)
  let drawn: number[] = [] // the change's look on the calendar, kept until a plan has it (plan/pending.ts)
  const instant = INSTANT[name]
  const shows = !!(optimistic || instant) // it changes what's on screen before the server answers
  if (shows) {
    await client.cancelQueries(matches)
    instant?.(client, input as never)
    if (optimistic) drawn = pending.collect(() => optimistic(client, input))
  }
  try {
    const out = await inTurn(laneOf(input), () => command(name, input))
    // The quick placement made after a change is the plan the calendar reads until the replan lands (the plan query
    // serves it), so it isn't drawn again as ghosts.
    const { command_id: id, generation } = out as { command_id: number | null; generation?: number | null }
    pending.settle(drawn, generation ?? 0)
    expectPlan(generation) // "Replanning…" until a plan has it (shell/ReplanStatus)
    const message = label ? label(out) : sentence(name)
    if (id !== null) {
      lastCommands = [id]
      if (!quiet) toast({ message, action: { label: "Undo", run: () => undo(client, toast, id) } })
    }
    return out
  } catch (error) {
    pending.drop(drawn)
    // What it showed at once goes back as it was when it was sent, and is read again in case anything came meanwhile;
    // one that showed nothing puts nothing back (the audit, 12 Nov: a failed pin put back the to-dos from before it,
    // over a refresh that came while it waited)
    if (shows) {
      for (const [key, data] of saved) client.setQueryData(key, data)
      staleSoon(client, OPTIMISTIC)
    }
    client.invalidateQueries({ queryKey: ["plan"] }) // drawn back as it was; read again in case some of it went through
    toast({ message: errorWords(error), tone: "error" })
    return undefined
  } finally {
    // A dropped stream's stand-in: while it's live its events refresh what changed (projects and exams too, 12 Nov: a
    // new project or prep didn't show without the stream), and this would only read it all a second time. Without it,
    // what the stream's events would have made stale (the audit, 12 Nov: a hand-kept list left settings, paces, areas,
    // repeats and calendars stale after a change).
    if (!streamLive) staleSoon(client, [...refreshFor("items.changed", name), ...refreshFor("plan.changed")])
  }
}

/** Several commands as one change (Claude's proposals, a triage option's steps), in order: in What if, those it
 * stages are staged like any other; one that fails takes back those before it; ⌘Z undoes them together. Their ids,
 * or null when one failed. */
export async function runTogether(client: QueryClient, toast: (toast: Toast) => void, steps: { command: string; input: unknown }[]): Promise<number[] | null> {
  const ids: number[] = []
  try {
    for (const step of steps) {
      if (whatIf.stages(step.command)) {
        whatIf.stage(step.command, step.input as Record<string, unknown>)
        continue
      }
      const out = await command(step.command as CommandName, step.input as never)
      if (out.command_id != null) ids.push(out.command_id)
    }
  } catch (error) {
    toast({ message: errorWords(error), tone: "error" })
    await undoAll(client, toast, ids)
    return null
  }
  rememberTogether(ids)
  return ids
}

export function useCommand<N extends CommandName>(name: N, options: Options<N> = {}) {
  const client = useQueryClient()
  const toast = useToast()
  const { optimistic, label, quiet } = options
  return useCallback(
    (input: CommandInput<N>) => runCommand(client, toast, name, input, { optimistic, label, quiet }),
    [client, toast, name, optimistic, label, quiet],
  )
}

const SAID: Record<string, string> = {
  add: "Added",
  done: "Marked done",
  drop: "Dropped",
  edit: "Saved",
  pin: "Pinned",
  progress: "Progress saved",
  reopen: "Reopened",
  shove: "Shoved",
  start: "Timer started",
  stop: "Timer stopped",
  unpin: "Unpinned",
}

function sentence(name: string): string {
  const words = name.replaceAll("_", " ")
  return SAID[name] ?? `${words[0].toUpperCase()}${words.slice(1)}`
}

export function undoLast(client: QueryClient, toast: (toast: Toast) => void): void {
  if (!lastCommands.length) return toast({ message: "Nothing to undo" })
  undoAll(client, toast, lastCommands)
  lastCommands = []
}

async function undo(client: QueryClient, toast: (toast: Toast) => void, id: number): Promise<void> {
  await undoAll(client, toast, [id])
}

/** Undo several commands, newest first, as one action. */
export async function undoAll(client: QueryClient, toast: (toast: Toast) => void, ids: number[]): Promise<void> {
  lastCommands = lastCommands.filter((id) => !ids.includes(id)) // undone from a toast: ⌘Z doesn't try it again
  try {
    for (const id of [...ids].reverse()) {
      await command("undo", { command_id: id })
    }
    toast({ message: "Undone" })
  } catch (error) {
    toast({ message: errorWords(error), tone: "error" })
  }
  client.invalidateQueries()
}
