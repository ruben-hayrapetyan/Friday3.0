// Every change goes through here (DESIGN §18.2): optimistic display, the command, ghosts, an Undo toast, and a
// rollback with the server's message on error. In What if, a change made on the Plan page is staged instead
// (`whatif/store.ts`): nothing is sent until you keep it.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { command, type CommandInput, type CommandName, errorWords, type Output } from "@/api/client"
import { type Toast, useToast } from "@/components/Toasts"
import { markedDone, mealEnded, mealSkipped, mealStarted, napEnded, napStarted, sleepMarked, timerStarted, timerStopped } from "@/now/instant"
import { pending } from "@/plan/pending"
import { whatIf } from "@/whatif/store"

// settings too: a look flipped on the calendar goes back when the server refuses it (audit, 8 Nov)
const OPTIMISTIC = ["items", "item", "plan", "now", "status", "meals", "sleep", "settings"]

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
    client.invalidateQueries({ queryKey: ["plan"] }) // drawn back as it was; read again in case some of it went through
    toast({ message: errorWords(error), tone: "error" })
    return undefined
  } finally {
    // The server's events refresh these too; this covers a dropped stream (projects and exams too, 12 Nov: a new
    // project or prep didn't show without the stream).
    client.invalidateQueries({ predicate: (q) => ["items", "item", "now", "status", "meals", "sleep", "duplicates", "to_review", "tokens", "gmail_app_accounts", "mail_app_accounts", "integrations", "integration_lists", "inbox", "projects", "exams"].includes(String(q.queryKey[0])) })
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
