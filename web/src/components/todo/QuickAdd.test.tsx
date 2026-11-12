// @vitest-environment happy-dom
// How a quick-add line reads as you type: only the line as it is now, never an answer for what it was a moment ago
// (the audit, 12 Nov: a slow answer for "essay fri" came after the box was emptied and showed its due on nothing).
import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useParsed } from "./QuickAdd"

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

/** Each parse answered when the test says, by the text it was asked about. */
function server() {
  const waiting = new Map<string, (r: Response) => void>()
  vi.stubGlobal("fetch", vi.fn((url: string) => new Promise<Response>((answer) => waiting.set(new URL(url, "http://x").searchParams.get("text") ?? "", answer))))
  return (text: string) => waiting.get(text)?.(new Response(JSON.stringify({ fields: { title: text }, spans: [] })))
}

describe("a quick-add line's reading", () => {
  it("drops an answer for what the line was once it has changed", async () => {
    vi.useFakeTimers()
    const answer = server()
    const { result, rerender } = renderHook(({ text }) => useParsed(text), { initialProps: { text: "essay fri" } })
    await act(async () => void vi.advanceTimersByTime(150)) // asked about "essay fri"
    rerender({ text: "" }) // added, and the box emptied
    await act(async () => void answer("essay fri"))
    expect(result.current).toBeNull()
    rerender({ text: "laundry" })
    await act(async () => void vi.advanceTimersByTime(150))
    await act(async () => void answer("laundry"))
    expect(result.current?.fields).toEqual({ title: "laundry" })
  })
})
