// Reads wait their turn, a few at a time, and commands never wait behind them (12 Nov: a click waited behind the
// page's thirty-odd reads after the click before it).
import { afterEach, describe, expect, it, vi } from "vitest"
import { command, laneOf, query, queryBody } from "./client"

describe("the order Friday is asked in", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("asks at most four things at once, and a command at once", async () => {
    const started: string[] = []
    const finish: (() => void)[] = []
    vi.stubGlobal("fetch", (url: string) => {
      started.push(url.replace(/\?.*/, ""))
      return new Promise((done) => finish.push(() => done(new Response("{}", { status: 200 }))))
    })
    const reads = Array.from({ length: 6 }, () => query("status" as never))
    await new Promise((r) => setTimeout(r, 0))
    expect(started).toHaveLength(4)
    const sent = command("done" as never, { id: 1 } as never)
    await new Promise((r) => setTimeout(r, 0))
    expect(started.at(-1)).toBe("/api/c/done") // didn't wait for the reads
    finish.splice(0).forEach((f) => f())
    await new Promise((r) => setTimeout(r, 0))
    expect(started.filter((u) => u === "/api/q/status")).toHaveLength(6) // the rest went as the first finished
    finish.splice(0).forEach((f) => f())
    await Promise.all([...reads, sent])
  })

  it("lets what plans your week (What if, a suggestion's effect, another way, the exact fit) take its own turns, so it never holds up the page's quick reads", async () => {
    const started: string[] = []
    const finish = new Map<string, (() => void)[]>()
    vi.stubGlobal("fetch", (url: string) => {
      const name = url.replace(/\?.*/, "").replace("/api/q/", "")
      started.push(name)
      return new Promise((done) => finish.set(name, [...(finish.get(name) ?? []), () => done(new Response("{}", { status: 200 }))]))
    })
    // four slow ones first, as a busy What if and the Inbox's effects would ask
    const slow = [
      queryBody("whatif" as never, {} as never),
      query("suggestion_effect" as never),
      query("other_way" as never),
      queryBody("fit" as never, { exact: true } as never),
    ]
    await new Promise((r) => setTimeout(r, 0))
    expect(started.filter((n) => n !== "status")).toHaveLength(2) // two at a time in their own lane
    const quick = Array.from({ length: 4 }, () => query("status" as never))
    await new Promise((r) => setTimeout(r, 0))
    expect(started.filter((n) => n === "status")).toHaveLength(4) // the page's reads didn't wait behind them
    for (const f of finish.get("status") ?? []) f()
    await Promise.all(quick)
    for (let round = 0; round < 3; round++) {
      for (const [name, fs] of finish) if (name !== "status") fs.splice(0).forEach((f) => f())
      await new Promise((r) => setTimeout(r, 0))
    }
    await Promise.all(slow)
    expect(started.filter((n) => n !== "status").sort()).toEqual(["fit", "other_way", "suggestion_effect", "whatif"])
  })

  it("knows which reads plan the week: the quick fit check is a quick read", () => {
    expect(["whatif", "suggestion_effect", "other_way"].map((n) => laneOf(n))).toEqual(["planning", "planning", "planning"])
    expect(laneOf("fit", { exact: true })).toBe("planning")
    expect(laneOf("fit", { exact: false })).toBe("quick")
    expect(["status", "plan", "items", "fits", "inbox"].map((n) => laneOf(n))).toEqual(["quick", "quick", "quick", "quick", "quick"])
  })
})
