// Everything being timed shows on the calendar while it runs, side by side (15 Nov, a client: only one of two timers
// showed until they were stopped).
import { describe, expect, it } from "vitest"
import { laneBox, timerLanes } from "./timerLanes"

describe("the timers drawn on the calendar", () => {
  it("draws the one timed alongside beside the main one, each half the column, counting on since the server said", () => {
    const lanes = timerLanes({ key: "main", title: "take notes on lecture 22", seconds: 1855 }, [{ item_id: 7, title: "fix up hq", elapsed_s: 1869 }], 30)
    expect(lanes.map((l) => [l.title, l.seconds, l.lane, l.lanes])).toEqual([
      ["take notes on lecture 22", 1855, 0, 2],
      ["fix up hq", 1899, 1, 2],
    ])
    expect(laneBox(1, 2)).toEqual({ left: "calc(50% + 3px)", width: "calc(50% - 6px)" })
  })
  it("one timer keeps the whole column; one timed alongside a planned block (drawn by the plan) gets it alone", () => {
    expect(timerLanes({ key: "main", title: "A", seconds: 60 }, [], 0).map((l) => l.lanes)).toEqual([1])
    expect(laneBox(0, 1)).toEqual({ left: "calc(0% + 3px)", width: "calc(100% - 6px)" })
    expect(timerLanes(null, [{ item_id: 3, title: "B", elapsed_s: 5 }], 0)).toEqual([{ key: "along-3", title: "B", seconds: 5, lane: 0, lanes: 1 }])
  })
})
