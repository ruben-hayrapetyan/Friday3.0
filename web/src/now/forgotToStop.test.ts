// "Forgot to stop?" (9 Nov: started at 5:34pm, pressed at 6:20pm, and the box went to 8:50am).
import { describe, expect, it } from "vitest"
import { nudgeFrom } from "@/components/fr/TimeInput"
import { spanOn, typedTime } from "@/lib/ampm"
import { toMin } from "@/lib/time"
import { stoppedGuess } from "./Dock"

const started = "2026-11-09T17:34"

describe("where the stop time starts (black box)", () => {
  it("opens at the time it is now, not 9am", () => {
    expect(stoppedGuess(toMin("2026-11-09T18:20"), toMin(started))).toBe("18:20")
    expect(stoppedGuess(toMin("2026-11-09T18:23"), toMin(started))).toBe("18:20") // the 5 minutes before
  })

  it("is never before the timer started", () => {
    expect(stoppedGuess(toMin("2026-11-09T17:37"), toMin(started))).toBe("17:35") // still after 5:34
    expect(stoppedGuess(toMin("2026-11-09T17:38"), toMin("2026-11-09T17:36"))).toBe("17:38") // 5:35 would be before
  })

  it("stops the same evening, not the next day", () => {
    const at = stoppedGuess(toMin("2026-11-09T18:20"), toMin(started))
    expect(spanOn(started.slice(0, 10), started.slice(11, 16), at).end).toBe("2026-11-09T18:20")
  })

  it("reads a time typed without am or pm as after the start", () => {
    expect(typedTime("6:05", "18:20", { after: "17:34", near: "18:20" })?.time).toBe("18:05")
  })

  it("counts past midnight for a timer started late", () => {
    const at = stoppedGuess(toMin("2026-11-10T00:42"), toMin("2026-11-09T23:10"))
    expect(at).toBe("00:40")
    expect(spanOn("2026-11-09", "23:10", at).end).toBe("2026-11-10T00:40")
  })
})

describe("where an empty box's arrows start (glass box)", () => {
  const now = new Date(2026, 10, 9, 18, 23)
  it("near what it expects, first", () => expect(nudgeFrom({ near: "18:20", after: "17:34" }, now)).toBe("18:20"))
  it("else just after what it comes after", () => expect(nudgeFrom({ after: "17:34" }, now)).toBe("17:34"))
  it("else the time it is now, to the 5 minutes", () => expect(nudgeFrom(undefined, now)).toBe("18:20"))
})
