import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Item } from "@/api/client"
import type { Toast } from "@/components/Toasts"
import { clearLanes, inTurn, laneOf, runCommand, runTogether, undoAll, undoLast } from "./useCommand"

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

afterEach(() => (vi.unstubAllGlobals(), clearLanes()))

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
    answer(422, { field: "id", message: "That item (T2) isn't there any more" })
    await runCommand(client, toast, "done", { id: 2 }, { optimistic: withoutItem })
    expect(client.getQueryData(["items"])).toEqual(items)
    expect(toasts).toEqual([{ message: "That item (T2) isn't there any more", tone: "error" }])
  })

  it("that fails with nothing shown for it leaves what was read meanwhile, not the list from before it", async () => {
    // the audit, 12 Nov: a failed pin put back the to-dos as they were when it was sent, over a refresh that came
    // while it waited, and with the stream live nothing read them again
    const { client, toasts, toast } = setup()
    let refuse = (_: Response) => {}
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((answer) => (refuse = answer))))
    const running = runCommand(client, toast, "pin", { id: 1, start: "2026-10-19T10:00", kind: "preferred" })
    const fresh = [...items, { id: 3, title: "added on the phone" }] as Item[]
    client.setQueryData(["items"], fresh) // a refresh lands while the pin waits
    refuse(new Response(JSON.stringify({ message: "That time is in the past" }), { status: 422 }))
    await running
    expect(client.getQueryData(["items"])).toEqual(fresh)
    expect(toasts).toEqual([{ message: "That time is in the past", tone: "error" }])
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
      if (name === fail) return new Response(JSON.stringify({ field: "id", message: "That item (T9) isn't there any more" }), { status: 422 })
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
    expect(toasts[0]).toEqual({ message: "That item (T9) isn't there any more", tone: "error" })
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

describe("a setting changed", () => {
  // the audit, 12 Nov: no setting showed before Friday answered, and two quick clicks each wrote the whole list back
  // from the settings as they were before either
  it("shows at once, the whole setting or only what it names for a setting saved in part, and goes back when refused", async () => {
    const { client, toast } = setup()
    const was = { calendar_look: { toolbar: ["Work"], show_past_plan: true }, pace: { default: "Normal", by_day: {} } }
    client.setQueryData(["settings"], was)
    let refuse = (_: Response) => {}
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((answer) => (refuse = answer))))
    const look = runCommand(client, toast, "settings_set", { key: "calendar_look", value: { toolbar: [], show_past_plan: false } })
    await vi.waitFor(() => expect(client.getQueryData(["settings"])).toMatchObject({ calendar_look: { toolbar: [], show_past_plan: false } }))
    refuse(new Response(JSON.stringify({ command_id: 4, result: { message: "Saved calendar_look" } })))
    await look
    const pace = runCommand(client, toast, "settings_set", { key: "pace", value: { by_day: { sat: "Easy" } } })
    await vi.waitFor(() => expect(client.getQueryData(["settings"])).toMatchObject({ pace: { default: "Normal", by_day: { sat: "Easy" } } }))
    refuse(new Response(JSON.stringify({ message: "No such pace" }), { status: 422 }))
    await pace
    expect(client.getQueryData<typeof was>(["settings"])?.pace).toEqual(was.pace)
  })

  it("is read again, with everything else a setting can change, when the live stream is down", async () => {
    const { client, toast } = setup()
    for (const key of ["settings", "paces", "areas", "series_list", "google_calendars", "mac_calendars", "documents", "calendar_repeats"]) client.setQueryData([key], {})
    answer(200, { command_id: 5, result: { message: "Saved calendar_look" } })
    await runCommand(client, toast, "settings_set", { key: "calendar_look", value: {} })
    await vi.waitFor(() => {
      for (const key of ["settings", "paces", "areas", "series_list", "google_calendars", "mac_calendars", "documents", "calendar_repeats"]) expect(client.getQueryState([key])?.isInvalidated, key).toBe(true)
    })
  })
})

describe("changes made quickly, one after another", () => {
  // 16 Nov: an ongoing project's hours set to 5h, then 4h, were sent at once and saved as 5h when the first finished last
  function held() {
    const answers: ((r: Response) => void)[] = []
    const fetch = vi.fn(() => new Promise<Response>((answer) => answers.push(answer)))
    vi.stubGlobal("fetch", fetch)
    const reply = (i: number) => answers[i](new Response(JSON.stringify({ command_id: i + 1, result: {} }), { status: 200 }))
    return { fetch, reply, bodies: () => fetch.mock.calls.map((c) => JSON.parse(String((c as unknown as [string, RequestInit])[1].body))) }
  }

  it("to the same thing go to the server in the order made, each once the one before is answered", async () => {
    const { client, toast } = setup()
    const { fetch, reply, bodies } = held()
    const first = runCommand(client, toast, "edit", { id: 1, duration_min: 300 })
    const second = runCommand(client, toast, "edit", { id: 1, duration_min: 240 })
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    await new Promise((r) => setTimeout(r, 20))
    expect(fetch).toHaveBeenCalledTimes(1) // the second waits for the first's answer
    reply(0)
    await first
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(bodies().map((b) => b.duration_min)).toEqual([300, 240])
    reply(1)
    await second
  })

  it("to the same thing still go when the one before is refused", async () => {
    const { client, toast } = setup()
    const answers: ((r: Response) => void)[] = []
    const fetch = vi.fn(() => new Promise<Response>((answer) => answers.push(answer)))
    vi.stubGlobal("fetch", fetch)
    const first = runCommand(client, toast, "edit", { id: 1, duration_min: 300 })
    const second = runCommand(client, toast, "edit", { id: 1, duration_min: 240 })
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    answers[0](new Response(JSON.stringify({ field: "id", message: "No" }), { status: 422 }))
    expect(await first).toBeUndefined()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    answers[1](new Response(JSON.stringify({ command_id: 2, result: {} }), { status: 200 }))
    expect(await second).toBeTruthy()
  })

  it("to different things go at once", async () => {
    const { client, toast } = setup()
    const { fetch, reply } = held()
    const one = runCommand(client, toast, "edit", { id: 1, duration_min: 300 })
    const two = runCommand(client, toast, "edit", { id: 2, duration_min: 240 })
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    reply(0)
    reply(1)
    await Promise.all([one, two])
  })

  it("wait for an earlier one that never answers only so long", async () => {
    vi.useFakeTimers()
    try {
      void inTurn("id 9", () => new Promise(() => {})) // a server that stopped answering
      const next = inTurn("id 9", async () => "sent")
      await vi.advanceTimersByTimeAsync(10_000)
      expect(await next).toBe("sent")
    } finally {
      vi.useRealTimers()
    }
  })

  it("are lined up by what they change: an id, a setting's key, a block", () => {
    expect(laneOf({ id: 4, hours_per_week: 5 })).toBe("id 4")
    expect(laneOf({ key: "time", value: {} })).toBe("key time")
    expect(laneOf({ block_key: "T1@2026-10-19T10:00" })).toBe("block T1@2026-10-19T10:00")
    expect(laneOf({ title: "New" })).toBeNull()
  })
})
