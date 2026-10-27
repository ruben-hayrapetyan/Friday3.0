import { describe, expect, it } from "vitest"
import { refreshFor } from "./events"

describe("server events", () => {
  it("refresh what each changes", () => {
    expect(refreshFor("items.changed")).toEqual(["*"])
    expect(refreshFor("plan.changed")).toEqual(expect.arrayContaining(["plan", "now", "items", "status"]))
    expect(refreshFor("plan.provisional")).toEqual(["plan"])
  })
})
