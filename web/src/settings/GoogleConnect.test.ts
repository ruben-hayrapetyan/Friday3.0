import { describe, expect, it } from "vitest"
import { connectLabel, type GoogleAccess, sentence, wantsSignIn } from "./GoogleConnect"

const NONE: GoogleAccess = { state: "idle", client_file: true, calendar: false, gmail: false, events: false }

describe("connecting Google", () => {
  it("says what the button does now: waiting while Google's page is open, else what it asks for", () => {
    expect(connectLabel(NONE, "calendar", false)).toBe("Connect Google")
    expect(connectLabel({ ...NONE, state: "waiting" }, "calendar", false)).toBe("Waiting for Google…")
    expect(connectLabel({ ...NONE, state: "waiting" }, "gmail", true)).toBe("Waiting for Google…")
    expect(connectLabel({ ...NONE, state: "failed" }, "calendar", false)).toBe("Connect Google")
    expect(connectLabel({ ...NONE, calendar: true }, "gmail", false)).toBe("Allow Gmail")
    expect(connectLabel({ ...NONE, calendar: true }, "calendar", true)).toBe("Connect again")
  })

  it("asks for a new sign-in only when Google turned the token away, not when Google is down", () => {
    expect(wantsSignIn("RefreshError: ('invalid_grant: Token has been expired or revoked.', {})")).toBe(true)
    expect(wantsSignIn('HttpError: <HttpError 403 "Request had insufficient authentication scopes.">')).toBe(true)
    expect(wantsSignIn("TimeoutError: timed out")).toBe(false)
    expect(wantsSignIn("LookupError: no longer in your Google account")).toBe(false)
    expect(wantsSignIn(null)).toBe(false)
  })

  it("says a refusal as a sentence, without the field's name", () => {
    expect(sentence("file: file: that isn't Google's key file. It's the .json file Google Cloud downloads")).toBe("That isn't Google's key file. It's the .json file Google Cloud downloads.")
    expect(sentence("google: Friday needs the key file from Google Cloud first")).toBe("Friday needs the key file from Google Cloud first.")
    expect(sentence("Network trouble!")).toBe("Network trouble!")
  })
})
