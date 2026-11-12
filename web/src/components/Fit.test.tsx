// @vitest-environment happy-dom
// Do I have time for this? Only for the change as it is now: a check of what it was a moment ago that failed late
// doesn't stand under the new one (the audit, 12 Nov).
import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useFit } from "./Fit"

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

/** Each check answered when the test says, by the title it was asked about. */
function server() {
  const waiting = new Map<string, (r: Response) => void>()
  vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise<Response>((answer) => waiting.set(JSON.parse(String(init.body)).input.title, answer))))
  return waiting
}

describe("the check for a change", () => {
  it("doesn't say the check of what the change was failed, once it has changed", async () => {
    vi.useFakeTimers()
    const waiting = server()
    const { result, rerender } = renderHook(({ title }) => useFit("add", { title, when: "fixed" }), { initialProps: { title: "Poker" } })
    await act(async () => void vi.advanceTimersByTime(450)) // "Poker" asked about
    rerender({ title: "Poker night" })
    await act(async () => void waiting.get("Poker")?.(new Response(JSON.stringify({ message: "Friday is busy" }), { status: 500 })))
    expect(result.current.error).toBeNull()
    await act(async () => void vi.advanceTimersByTime(450))
    await act(async () => void waiting.get("Poker night")?.(new Response(JSON.stringify({ verdict: "fits", said: "You have time", exact: false }))))
    expect(result.current.error).toBeNull()
    expect(result.current.fit?.verdict).toBe("fits")
  })
})
