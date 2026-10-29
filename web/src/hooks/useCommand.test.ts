import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Item } from "@/api/client"
import type { Toast } from "@/components/Toasts"
import { runCommand, undoAll } from "./useCommand"

const items = [{ id: 1, title: "PS5" }, { id: 2, title: "laundry" }] as Item[]
const withoutItem = (client: QueryClient, input: { id: number }) =>
  client.setQueryData<Item[]>(["items"], (all) => all?.filter((i) => i.id !== input.id))

function answer(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })))
}

function setup() {
  const client = new QueryClient()
  client.setQueryData(["items"], items)
  const toasts: Toast[] = []
  return { client, toasts, toast: (t: Toast) => toasts.push(t) }
}

afterEach(() => vi.unstubAllGlobals())

describe("a command", () => {
  it("shows its change at once and offers undo; its quick placement comes with the plan, not as ghosts", async () => {
    const { client, toasts, toast } = setup()
    const ghost = { key: "T1@2026-10-19T10:00", item_id: 1, title: "PS5", start: "2026-10-19T10:00", end: "2026-10-19T11:00" }
    answer(200, { command_id: 7, result: { item: {} }, provisional: [ghost] })
    const running = runCommand(client, toast, "done", { id: 2 }, { optimistic: withoutItem })
    await vi.waitFor(() => expect(client.getQueryData<Item[]>(["items"])?.map((i) => i.id)).toEqual([1]))
    await running
    expect(client.getQueryData(["ghosts"])).toBeUndefined()
    expect(toasts.map((t) => [t.message, t.action?.label])).toEqual([["Marked done", "Undo"]])
  })

  it("rolls back and shows the server's message when it fails", async () => {
    const { client, toasts, toast } = setup()
    answer(422, { field: "id", message: "no item T2" })
    await runCommand(client, toast, "done", { id: 2 }, { optimistic: withoutItem })
    expect(client.getQueryData(["items"])).toEqual(items)
    expect(toasts).toEqual([{ message: "id: no item T2", tone: "error" }])
  })

  it("undoes several commands newest first, as one action", async () => {
    const { client, toasts, toast } = setup()
    const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify({ command_id: null, result: {} })))
    vi.stubGlobal("fetch", fetch)
    await undoAll(client, toast, [3, 4, 5])
    const undone = fetch.mock.calls.map(([, init]) => JSON.parse(String(init.body)).command_id)
    expect(undone).toEqual([5, 4, 3])
    expect(toasts.map((t) => t.message)).toEqual(["Undone"])
  })
})

describe("a nap", () => {
  it("shows in the Now bar the moment you tap, with no other sleep tap, and goes when you're up", async () => {
    const { client, toast } = setup()
    client.setQueryData(["sleep"], { on: true, next: "done", napping: null })
    answer(200, { command_id: 9, result: { message: "Napping since 2:10pm" } })
    await runCommand(client, toast, "nap_start", {})
    const sleep = client.getQueryData<{ next: string | null; napping: { start: string } | null }>(["sleep"])
    expect(sleep?.next).toBeNull()
    expect(sleep?.napping?.start).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/)
    answer(200, { command_id: 10, result: { message: "Nap: 25 min" } })
    await runCommand(client, toast, "nap_end", {})
    expect(client.getQueryData<{ napping: unknown }>(["sleep"])?.napping).toBeNull()
  })
})
