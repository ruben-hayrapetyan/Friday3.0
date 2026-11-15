// @vitest-environment happy-dom
// Updates that show (15 Nov, the user: "whenever there is a new version, the popup shows up"): the window asks the
// server to look whenever it opens or comes back into view, at most once in ten minutes (H208), and a popup closed
// for one version opens again for a newer one (H209).
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const sent: string[] = []
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  command: vi.fn(async (name: string) => (sent.push(name), { result: {} })),
}))

const { forgetLooking, LOOK_AGAIN_MS, popupOpen, useLookWhenOpened } = await import("./updates")
type Status = Parameters<typeof popupOpen>[0]

const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
const version = (v: string) => ({ version: v, released: "2026-11-07", summary: v, new: [], changed: [], fixed: [] })
const status = (over: Partial<Status>): Status => ({ checks: true, have: "0.4.1", state: "idle", progress: 0, versions: [], popup: false, whats_new: [], restart: "now", ...over }) as Status

describe("the window looks for a new version when it opens", () => {
  beforeEach(() => (sent.length = 0, forgetLooking(), vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-15T12:00:00") })))
  afterEach(() => vi.useRealTimers())

  it("looks as it opens, and again when it comes back into view ten minutes on, not sooner", async () => {
    renderHook(() => useLookWhenOpened(true), { wrapper })
    expect(sent).toEqual(["update_check"])
    vi.setSystemTime(Date.now() + LOOK_AGAIN_MS - 1000)
    await act(async () => void document.dispatchEvent(new Event("visibilitychange")))
    expect(sent).toEqual(["update_check"])
    vi.setSystemTime(Date.now() + 2000)
    await act(async () => void document.dispatchEvent(new Event("visibilitychange")))
    expect(sent).toEqual(["update_check", "update_check"])
  })

  it("never looks in a Friday that doesn't look for updates (built from its code)", () => {
    renderHook(() => useLookWhenOpened(false), { wrapper })
    expect(sent).toEqual([])
  })
})

describe("the popup", () => {
  it("stays closed for the version you closed it on, and opens again for a newer one", () => {
    const offered = status({ popup: true, versions: [version("0.4.2")] })
    expect(popupOpen(offered, false, null)).toBe(true)
    expect(popupOpen(offered, false, "0.4.2")).toBe(false)
    expect(popupOpen(status({ popup: true, versions: [version("0.4.3"), version("0.4.2")] }), false, "0.4.2")).toBe(true)
    expect(popupOpen(status({ popup: false, versions: [version("0.4.2")] }), true, "0.4.2")).toBe(true) // asked for
  })
})
