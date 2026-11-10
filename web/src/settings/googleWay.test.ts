// How Google comes in (C77): only your own Friday, which carries Google's client, offers Google's own connection.
import { describe, expect, it } from "vitest"
import { googleWay } from "./GoogleConnect"

describe("how Google comes in", () => {
  it("a download (no Google client) lists Gmail itself in Setup, and Google's connection only under Advanced", () => {
    const way = googleWay(false)
    expect(way.direct).toBe(false)
    expect(way.setupMore).toBe("") // no More: Gmail is in Setup's list, with its form (C81)
    expect(way.settingsMore).toMatch(/^Advanced: .*Google Cloud key of your own/)
  })

  it("your own Friday (with the client) keeps Google's own connection under More", () => {
    const way = googleWay(true)
    expect(way.direct).toBe(true)
    expect(way.setupMore).toContain("connecting to Google directly")
  })
})
