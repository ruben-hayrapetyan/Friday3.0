// Everything being timed shows on the calendar while it runs, side by side (15 Nov, a client: only one of two timers
// showed until they were stopped).
import { describe, expect, it } from "vitest"
import { laneBox, spanIn, timerLanes } from "./timerLanes"

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

describe("a timer's part of a day's column", () => {
  // 17 Nov, the user: "when tasks roll over to the next day it doesn't show progress from the previous day" (timed
  // since 9:43pm, at 12:18am Monday's column showed nothing of it)
  const monday = 0
  const tuesday = 1440
  const now = tuesday + 18 // 12:18am Tuesday
  const seconds = (now - (monday + 21 * 60 + 43)) * 60 // since 9:43pm Monday

  it("shows in the day it began, from its start to midnight", () => {
    expect(spanIn(now, seconds, monday, monday + 1440)).toEqual({ top: 21 * 60 + 43, minutes: 2 * 60 + 17 })
  })
  it("and in today's, from midnight to now", () => {
    expect(spanIn(now, seconds, tuesday, tuesday + 1440)).toEqual({ top: 0, minutes: 18 })
  })
  it("in no day it doesn't reach", () => {
    expect(spanIn(now, seconds, tuesday + 1440, tuesday + 2880)).toBeNull()
    expect(spanIn(now, seconds, monday - 1440, monday)).toBeNull()
  })
  it("within a column that starts at 7am, cut to it", () => {
    expect(spanIn(monday + 600, 3 * 3600, monday + 420, monday + 1440)).toEqual({ top: 0, minutes: 180 })
  })
})
