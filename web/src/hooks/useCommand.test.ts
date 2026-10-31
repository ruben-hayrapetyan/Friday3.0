import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Item } from "@/api/client"
import type { Toast } from "@/components/Toasts"
import { runCommand, runTogether, undoAll, undoLast } from "./useCommand"

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

describe("several commands as one change (Ask Claude's, a triage option's)", () => {
  // the audit, 31 Oct: Claude's changes applied, then ⌘Z undid the pin made before them
  const server = (fail?: string) => {
    let id = 20
    const fetch = vi.fn(async (url: string, init: RequestInit) => {
      const name = String(url).split("/api/c/")[1]
      if (name === fail) return new Response(JSON.stringify({ field: "id", message: "no item T9" }), { status: 422 })
      return new Response(JSON.stringify({ command_id: name === "undo" ? null : ++id, result: { undone: JSON.parse(String(init.body)).command_id } }))
    })
    vi.stubGlobal("fetch", fetch)
    return fetch
  }
  const sent = (fetch: ReturnType<typeof server>) => fetch.mock.calls.map(([url, init]) => [String(url).split("/api/c/")[1], JSON.parse(String(init.body)).command_id ?? null])

  it("run in order, and ⌘Z takes them all back, newest first", async () => {
    const { client, toast } = setup()
    const fetch = server()
    expect(await runTogether(client, toast, [{ command: "edit", input: { id: 1 } }, { command: "pin", input: { id: 2 } }])).toEqual([21, 22])
    undoLast(client, toast)
    await vi.waitFor(() => expect(sent(fetch).slice(2)).toEqual([["undo", 22], ["undo", 21]]))
  })

  it("one that fails takes back those before it, and says why", async () => {
    const { client, toasts, toast } = setup()
    const fetch = server("pin")
    expect(await runTogether(client, toast, [{ command: "edit", input: { id: 1 } }, { command: "pin", input: { id: 9 } }])).toBeNull()
    expect(sent(fetch)).toEqual([["edit", null], ["pin", null], ["undo", 21]])
    expect(toasts[0]).toEqual({ message: "id: no item T9", tone: "error" })
  })

  it("undone from the toast, ⌘Z doesn't try them again", async () => {
    const { client, toasts, toast } = setup()
    server()
    const ids = (await runTogether(client, toast, [{ command: "edit", input: { id: 1 } }])) as number[]
    await undoAll(client, toast, ids)
    undoLast(client, toast)
    expect(toasts.at(-1)?.message).toBe("Nothing to undo")
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
