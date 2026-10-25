// Every change goes through here (DESIGN §18.2): optimistic display, the command, ghosts, an Undo toast, and a
// rollback with the server's message on error.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { ApiError, type CommandInput, type CommandName, command, type Output } from "@/api/client"
import { setGhosts } from "@/api/events"
import { type Toast, useToast } from "@/components/Toasts"

const OPTIMISTIC = ["items", "item", "plan", "now"]

// The newest command this page ran, for ⌘Z.
let lastCommand: number | null = null

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
  const matches = { predicate: (q: { queryKey: readonly unknown[] }) => OPTIMISTIC.includes(String(q.queryKey[0])) }
  const saved = client.getQueriesData(matches)
  if (optimistic) {
    await client.cancelQueries(matches)
    optimistic(client, input)
  }
  try {
    const out = await command(name, input)
    const { provisional, command_id: id } = out as { provisional?: unknown; command_id: number | null }
    if (Array.isArray(provisional)) setGhosts(client, provisional)
    const message = label ? label(out) : sentence(name)
    if (id !== null) {
      lastCommand = id
      if (!quiet) toast({ message, action: { label: "Undo", run: () => undo(client, toast, id) } })
    }
    return out
  } catch (error) {
    for (const [key, data] of saved) client.setQueryData(key, data)
    toast({ message: error instanceof ApiError ? error.message : String(error), tone: "error" })
    return undefined
  } finally {
    // The server's events refresh these too; this covers a dropped stream.
    client.invalidateQueries({ predicate: (q) => ["items", "item", "now", "status", "duplicates", "to_review"].includes(String(q.queryKey[0])) })
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
  if (lastCommand === null) return toast({ message: "Nothing to undo" })
  undo(client, toast, lastCommand)
  lastCommand = null
}

async function undo(client: QueryClient, toast: (toast: Toast) => void, id: number): Promise<void> {
  await undoAll(client, toast, [id])
}

/** Undo several commands, newest first, as one action. */
export async function undoAll(client: QueryClient, toast: (toast: Toast) => void, ids: number[]): Promise<void> {
  try {
    for (const id of [...ids].reverse()) {
      const out = await command("undo", { command_id: id })
      if (out.provisional) setGhosts(client, out.provisional)
    }
    toast({ message: "Undone" })
  } catch (error) {
    toast({ message: error instanceof ApiError ? error.message : String(error), tone: "error" })
  }
  client.invalidateQueries()
}
