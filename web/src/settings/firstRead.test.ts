// The first read's spinner (13 Nov), glass box: what a connected integration's box says while it's read for the
// first time, and when the page asks again by itself for what's connected.
import { describe, expect, it } from "vitest"
import { integrationStatus } from "./Integrations"
import { pollWhile, READING_POLL_MS } from "./TokenIntegration"

type Row = { last_error: string | null; reading: boolean }
const row = (over: Partial<Row> = {}): Row => ({ last_error: null, reading: false, ...over })
const asked = (data?: Row[]) => ({ state: { data: data as never } })

describe("a connected integration's box", () => {
  it("spins while its first read runs, then says connected", () => {
    expect(integrationStatus([row({ reading: true })])).toEqual(["Reading", "var(--color-accent-300)", true, true])
    expect(integrationStatus([row()])).toEqual(["Connected", "var(--color-accent-300)", true, false])
  })

  it("says a problem rather than spinning, and nothing when it isn't connected", () => {
    expect(integrationStatus([row({ reading: true, last_error: "Todoist is having trouble (503)" })])).toEqual(["Needs a look", "var(--fr-warn)", true])
    expect(integrationStatus([row(), row({ reading: true })])?.[3]).toBe(true) // a second account still being read
    expect(integrationStatus([])).toBeNull()
  })
})

describe("asking again for what's connected", () => {
  it("every moment while one is read for the first time, or a sign-in page is open; otherwise not", () => {
    expect(pollWhile(false)(asked([row({ reading: true })]))).toBe(READING_POLL_MS)
    expect(pollWhile(true)(asked([]))).toBe(READING_POLL_MS)
    expect(pollWhile(false)(asked([row(), row()]))).toBe(false)
    expect(pollWhile(false)(asked(undefined))).toBe(false)
    expect(READING_POLL_MS).toBeLessThanOrEqual(2000) // the spinner gives way within a couple of seconds
  })
})
