import { describe, expect, it } from "vitest"
import { minutesBetween } from "./Times"

describe("how long a meal or a night is", () => {
  it("counts from one time to the next, over midnight when it ends earlier", () => {
    expect(minutesBetween("12:30", "13:05")).toBe(35)
    expect(minutesBetween("23:40", "07:55")).toBe(495) // a night
    expect(minutesBetween("12:30", "12:30")).toBe(0)
    expect(minutesBetween("", "13:00")).toBeNull()
  })
})
