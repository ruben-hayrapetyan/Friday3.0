// When Settings' Google section opens by itself (C81: Gmail by app password opened it, and its key-file card made
// Google look calendar-only).
import { describe, expect, it } from "vitest"
import { advancedOpens } from "./Integrations"

const download = { direct: false, googleCalendar: false, gmailOn: false, macCalendars: true }

describe("Settings' Google section opening by itself", () => {
  it("stays closed in a download when Gmail is connected with an app password", () => {
    expect(advancedOpens({ ...download, gmailOn: true })).toBe(false)
  })
  it("stays closed in a download without Mac calendars", () => {
    expect(advancedOpens({ ...download, macCalendars: false })).toBe(false)
  })
  it("opens wherever Google's own connection is in use", () => {
    expect(advancedOpens({ ...download, googleCalendar: true })).toBe(true)
  })
  it("in your own Friday, opens while Gmail is on, as before", () => {
    expect(advancedOpens({ ...download, direct: true, gmailOn: true })).toBe(true)
  })
})
