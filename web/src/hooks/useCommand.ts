// Every change goes through here (DESIGN §18.2): optimistic display, the command, ghosts, an Undo toast, and a
// rollback with the server's message on error. In What if, a change made on the Plan page is staged instead
// (`whatif/store.ts`): nothing is sent until you keep it.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { ApiError, type CommandInput, type CommandName, command, type Output } from "@/api/client"
import { type Toast, useToast } from "@/components/Toasts"
import { markedDone, mealEnded, mealSkipped, mealStarted, napEnded, napStarted, sleepMarked, timerStarted, timerStopped } from "@/now/instant"
import { pending } from "@/plan/pending"
import { whatIf } from "@/whatif/store"

const OPTIMISTIC = ["items", "item", "plan", "now", "status", "meals", "sleep"]

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
  if (optimistic || instant) {
    await client.cancelQueries(matches)
    instant?.(client, input as never)
    if (optimistic) drawn = pending.collect(() => optimistic(client, input))
  }
  try {
    const out = await command(name, input)
    // The quick placement made after a change is the plan the calendar reads until the replan lands (the plan query
    // serves it), so it isn't drawn again as ghosts.
    const { command_id: id, generation } = out as { command_id: number | null; generation?: number | null }
    pending.settle(drawn, generation ?? 0)
    const message = label ? label(out) : sentence(name)
    if (id !== null) {
      lastCommands = [id]
      if (!quiet) toast({ message, action: { label: "Undo", run: () => undo(client, toast, id) } })
    }
    return out
  } catch (error) {
    pending.drop(drawn)
    for (const [key, data] of saved) client.setQueryData(key, data)
    toast({ message: error instanceof ApiError ? error.message : String(error), tone: "error" })
    return undefined
  } finally {
    // The server's events refresh these too; this covers a dropped stream.
    client.invalidateQueries({ predicate: (q) => ["items", "item", "now", "status", "meals", "sleep", "duplicates", "to_review"].includes(String(q.queryKey[0])) })
  }
}

export function useCommand<N extends CommandName>(name: N, options: Options<N> = {}) {
  const client = useQueryClient()
  const toast = useToast()
  const { optimistic, label } = options
  return useCallback(
    (input: CommandInput<N>) => runCommand(client, toast, name, input, { optimistic, label }),
    [client, toast, name, optimistic, label],
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
  try {
    for (const id of [...ids].reverse()) {
      await command("undo", { command_id: id })
    }
    toast({ message: "Undone" })
  } catch (error) {
    toast({ message: error instanceof ApiError ? error.message : String(error), tone: "error" })
  }
  client.invalidateQueries()
}
