import { describe, expect, it } from "vitest"
import { asFetchable, freeName, looksLikeALink } from "./LinkIntegration"
import { tagName } from "./TagsKinds"

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

describe("a name for what's added", () => {
  it("is one no link has: two Google links, or one added after another was removed", () => {
    expect(freeName("Google Calendar", [])).toBe("Google Calendar")
    expect(freeName("Google Calendar", ["Google Calendar"])).toBe("Google Calendar 2")
    // Blackboard and Blackboard 2 added, Blackboard removed: the next isn't Blackboard 2 again
    expect(freeName("Blackboard", ["Blackboard 2"])).toBe("Blackboard")
    expect(freeName("Blackboard", ["Blackboard", "Blackboard 2"])).toBe("Blackboard 3")
  })

  it("is a tag name no tag has, archived ones too", () => {
    expect(tagName(2, ["Tag 1"])).toBe("Tag 2")
    // Tag 1 archived, Tag 2 left: the next is Tag 3, not Tag 2 again
    expect(tagName(2, ["Tag 1", "Tag 2"])).toBe("Tag 3")
    expect(tagName(1, ["tag 1"])).toBe("Tag 2")
  })
})
