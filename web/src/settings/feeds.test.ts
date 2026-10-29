import { describe, expect, it } from "vitest"
import { feedName, feedUrl } from "./Integrations"

describe("a calendar link pasted in", () => {
  it("is fetched over https, a webcal:// link too (Canvas's, Outlook's)", () => {
    expect(feedUrl("  webcal://canvas.cornell.edu/feeds/calendars/user_abc.ics ")).toBe("https://canvas.cornell.edu/feeds/calendars/user_abc.ics")
    expect(feedUrl("https://example.edu/cal.ics")).toBe("https://example.edu/cal.ics")
  })

  it("is named for where it's from: Google's and Outlook's by name (29 Oct: Google's private link is the simple way)", () => {
    expect(feedName("https://calendar.google.com/calendar/ical/me%40gmail.com/private-abc/basic.ics")).toBe("Google Calendar")
    expect(feedName("https://outlook.office365.com/owa/calendar/abc/reachcalendar.ics")).toBe("Outlook")
    expect(feedName("webcal://outlook.live.com/owa/calendar/abc/calendar.ics")).toBe("Outlook")
    expect(feedName("https://www.canvas.cornell.edu/feeds/x.ics")).toBe("canvas")
    expect(feedName("not a link")).toBe("Feed")
  })
})
