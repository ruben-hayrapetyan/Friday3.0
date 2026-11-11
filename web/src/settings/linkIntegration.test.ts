import { describe, expect, it } from "vitest"
import { asFetchable, looksLikeALink } from "./LinkIntegration"

describe("a pasted calendar link", () => {
  it("is fetched over https when a calendar app's webcal:// is pasted", () => {
    expect(asFetchable(" webcal://example.edu/feed.ics ")).toBe("https://example.edu/feed.ics")
    expect(asFetchable("webcals://example.edu/feed.ics")).toBe("https://example.edu/feed.ics")
    expect(asFetchable("https://example.edu/feed.ics")).toBe("https://example.edu/feed.ics")
  })
  it("must look like a link before it can be added", () => {
    expect(looksLikeALink("https://moodle.example.edu/calendar/export_execute.php?userid=1")).toBe(true)
    expect(looksLikeALink("webcal://example.com/x.ics")).toBe(true)
    expect(looksLikeALink("my calendar")).toBe(false)
    expect(looksLikeALink("https://")).toBe(false)
  })
})
