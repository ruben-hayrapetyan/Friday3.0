// Reads wait their turn, a few at a time, and commands never wait behind them (12 Nov: a click waited behind the
// page's thirty-odd reads after the click before it).
import { afterEach, describe, expect, it, vi } from "vitest"
import { command, query } from "./client"

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
})
