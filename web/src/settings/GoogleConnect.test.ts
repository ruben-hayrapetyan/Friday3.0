import { describe, expect, it } from "vitest"
import { type Schemas } from "@/api/client"
import { signInAgain } from "./GoogleAccounts"
import { accountName, connectLabel, type GoogleAccess, type GoogleAccount, sentence, wantsSignIn } from "./GoogleConnect"

const NONE: GoogleAccess = { state: "idle", client_file: true, calendar: false, gmail: false, events: false }
const ME: GoogleAccount = { email: "me@gmail.com", gmail: true, events: true }
const SCHOOL: GoogleAccount = { email: "student@school.edu", gmail: false, events: true }
const calendar = (name: string, account: string, more: Partial<Schemas["GoogleCalendarOut"]> = {}): Schemas["GoogleCalendarOut"] => ({ id: name, name, primary: false, on: true, kind: "auto", trusted: false, last_sync: null, error: null, account, ...more })

describe("connecting Google", () => {
  it("says what the button does now: waiting while Google's page is open, else what it asks for", () => {
    expect(connectLabel(NONE, "calendar", false)).toBe("Connect Google")
    expect(connectLabel({ ...NONE, state: "waiting" }, "calendar", false)).toBe("Waiting for Google…")
    expect(connectLabel({ ...NONE, state: "waiting" }, "gmail", true)).toBe("Waiting for Google…")
    expect(connectLabel({ ...NONE, state: "failed" }, "calendar", false)).toBe("Connect Google")
    expect(connectLabel({ ...NONE, calendar: true }, "gmail", false)).toBe("Allow Gmail")
    expect(connectLabel({ ...NONE, calendar: true }, "calendar", true)).toBe("Connect again")
  })

  it("adds another account once one is connected, and waits only on the button whose sign-in it is", () => {
    const one = { ...NONE, calendar: true, accounts: [ME] }
    expect(connectLabel(one, "calendar", false)).toBe("Add another Google account")
    const allowing = { ...one, state: "waiting" as const, account: "student@school.edu" }
    expect(connectLabel(allowing, "gmail", false, "student@school.edu")).toBe("Waiting for Google…")
    expect(connectLabel(allowing, "calendar", false)).toBe("Add another Google account")
    expect(connectLabel({ ...one, state: "waiting" as const }, "calendar", false)).toBe("Waiting for Google…")
  })

  it("asks an account to sign in again only for its own trouble", () => {
    const expired = calendar("DSA", "student@school.edu", { error: "RefreshError: ('invalid_grant: Token has been expired or revoked.', {})" })
    expect(signInAgain(SCHOOL, [expired, calendar("Family", "me@gmail.com")])).toMatch(/expired/)
    expect(signInAgain(ME, [expired, calendar("Family", "me@gmail.com")])).toBeNull()
    expect(signInAgain({ ...ME, mail_error: "RefreshError: invalid_grant" }, [])).toMatch(/expired/)
    expect(signInAgain({ ...ME, events: false }, [calendar("Family", "me@gmail.com", { editable: true })])).toMatch(/changes/)
    expect(signInAgain({ ...ME, events: false }, [calendar("Family", "me@gmail.com")])).toBeNull()
  })

  it("names the account from before Friday kept several until its address is known", () => {
    expect(accountName("")).toBe("Your Google account")
    expect(accountName("me@gmail.com")).toBe("me@gmail.com")
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
