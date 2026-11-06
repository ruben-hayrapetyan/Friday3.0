// Other ways as a dialogue (6 Nov: "it just says the same static thing for over 20 seconds"): each way shows as it
// comes, the one being planned counts its seconds against how long the last took, and past eight seconds you're told
// you can close the window. Glass box: the rules in finding.ts. Black box: the search against a stand-in server.
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Schemas } from "@/api/client"
import { begin, failed, finding, found, heading, slots, stale, stopped } from "./finding"

type Way = Schemas["OtherWay"]
const way = (seed: number, signature = `s${seed}`): Way => ({ weights: {}, seed, summary: `Way from ${seed}`, blocks: [], hours: 4, sessions: 3, late: {}, rule_totals: {}, signature })

describe("the rules", () => {
  it("keeps each way that's new, and times the next from when this one came", () => {
    const f = found(begin(1, 0, null), way(1), 6, 2, 30_000)
    expect(f.ways.map((w) => w.seed)).toEqual([1])
    expect([f.lastMs, f.wayBegan, f.state]).toEqual([30_000, 30_000, "planning"])
  })
  it("drops a way it has already, and one that came out as your plan", () => {
    let f = found(begin(1, 0, null), way(1, "same"), 6, 2, 10)
    f = found(f, way(2, "same"), 6, 2, 20)
    f = found(f, null, 6, 2, 30)
    expect([f.ways.length, f.tried]).toEqual([1, 3])
  })
  it("is done with two ways, or when the seeds run out", () => {
    expect(found(found(begin(1, 0, null), way(1), 6, 2, 1), way(2), 6, 2, 2).state).toBe("done")
    let f = begin(1, 0, null)
    for (let i = 0; i < 6; i++) f = found(f, null, 6, 2, i)
    expect([f.state, f.ways]).toEqual(["done", []])
  })
  it("says what each slot is doing, the seconds, and how far against the last way", () => {
    const f = found(begin(1, 0, 40_000), way(1), 6, 2, 30_000)
    const [first, second] = slots(f, 45_000)
    expect(first.way?.seed).toBe(1)
    expect(second).toEqual({ line: "Planning way 2… 15s", share: 0.5 })
    expect(slots(begin(1, 0, null), 3_000)).toEqual([
      { line: "Planning way 1… 3s", share: null },
      { line: "Next", share: null },
    ])
  })
  it("says so when a try came out like your plan", () => {
    const f = found(begin(1, 0, 30_000), null, 6, 2, 30_000)
    expect(slots(f, 31_000)[0].line).toBe("Planning way 1… 1s, another try: the last came out like yours")
  })
  it("never says it's nearly done when it's taking longer than the last: the bar moves instead", () => {
    const f = begin(1, 0, 10_000)
    expect(slots(f, 9_900)[0].share).toBe(0.95)
    expect(slots(f, 60_000)[0].share).toBeNull()
  })
  it("tells you past eight seconds that you needn't wait", () => {
    expect(heading(begin(1, 0, null), 7_999).note).toBeNull()
    expect(heading(begin(1, 0, null), 8_000).note).toMatch(/close this and keep working/)
    expect(heading(begin(1, 0, 32_000), 0).line).toBe("Planning your week two more ways, about 30s each. Each shows here as it's ready.")
    expect(heading(found(begin(1, 0, null), way(1), 6, 2, 1), 2).line).toMatch(/1 of 2 ready/)
  })
  it("says how it ended", () => {
    expect(heading(stopped(begin(1, 0, null)), 0).line).toBe("Stopped.")
    expect(heading(failed(begin(1, 0, null), "server down"), 0).line).toBe("Couldn't plan other ways: server down")
    let none = begin(1, 0, null)
    for (let i = 0; i < 6; i++) none = found(none, null, 6, 2, i)
    expect(heading(none, 0).line).toMatch(/Nothing much else would change/)
    let one = found(begin(1, 0, null), way(1), 6, 2, 0)
    for (let i = 0; i < 5; i++) one = found(one, null, 6, 2, i)
    expect(heading(one, 0).line).toMatch(/Only one came out different/)
  })
  it("shows ways found a few minutes ago again, and plans afresh after ten", () => {
    const done = found(found(begin(1, 0, null), way(1), 6, 2, 1), way(2), 6, 2, 2)
    expect(stale(done, 5 * 60_000)).toBe(false)
    expect(stale(done, 11 * 60_000)).toBe(true)
    expect(stale(null, 0)).toBe(true)
    expect(stale(begin(1, 0, null), 60 * 60_000)).toBe(false) // still planning: not started again
  })
})

describe("the search, against a stand-in server", () => {
  afterEach(() => vi.unstubAllGlobals())
  const serve = (answers: (Way | null)[]) => {
    const asked: number[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const seed = Number(new URL(url, "http://x").searchParams.get("seed"))
        asked.push(seed)
        return new Response(JSON.stringify({ way: answers[seed - 1] ?? null, tries: 6, wanted: 2 }), { headers: { "content-type": "application/json" } })
      }),
    )
    return asked
  }

  it("asks one seed at a time until two ways unlike each other, and says so once the window is closed", async () => {
    const asked = serve([way(1, "a"), way(2, "a"), null, way(4, "b")])
    const ready = vi.fn()
    finding.open(false)
    await finding.start(ready)
    expect(asked).toEqual([1, 2, 3, 4])
    expect(finding.get()?.ways.map((w) => w.seed)).toEqual([1, 4])
    expect(ready).toHaveBeenCalledOnce()
  })
  it("doesn't interrupt you with a toast while the window shows them", async () => {
    serve([way(1), way(2)])
    const ready = vi.fn()
    finding.open(true)
    await finding.start(ready)
    expect(finding.get()?.state).toBe("done")
    expect(ready).not.toHaveBeenCalled()
    finding.open(false)
  })
  it("stops asking once you stop, keeping what it found", async () => {
    const asked = serve([way(1), way(2)])
    const going = finding.start(() => undefined)
    finding.stop()
    await going
    expect(finding.get()?.state).toBe("stopped")
    expect(asked.length).toBeLessThanOrEqual(1)
  })
})
