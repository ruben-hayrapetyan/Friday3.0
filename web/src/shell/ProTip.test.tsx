// @vitest-environment happy-dom
// Pro tips (#23, 24 Nov, the user: "slides in for 5s", then "show up for 10seconds and have a 'take me there'
// button"): when it comes, how long it stays, its button, and never over the tour.
import { act, render, screen } from "@testing-library/react"
import { useEffect } from "react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const sent: string[] = []
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  query: vi.fn(async () => ({ id: "timing", text: "Time your work from the Now bar, and Friday learns how long things take.", page: "/" })),
  command: vi.fn(async (name: string) => (sent.push(name), { result: { message: "Shown" } })),
}))

const { ProTip, TIP_AFTER_MS, TIP_FOR_MS } = await import("./ProTip")
const { ShellProvider, useShell } = await import("./ShellContext")
const TEXT = "Time your work from the Now bar, and Friday learns how long things take."

function TourOpen() {
  const { setTour } = useShell()
  useEffect(() => setTour(true), [setTour])
  return null
}

const open = (touring = false) =>
  render(
    <MemoryRouter>
      <ShellProvider today="2026-11-24">
        {touring && <TourOpen />}
        <ProTip />
      </ShellProvider>
    </MemoryRouter>,
  )
const after = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)))

describe("a pro tip's ten seconds", () => {
  beforeEach(() => (sent.length = 0, vi.useFakeTimers()))
  afterEach(() => vi.useRealTimers())

  it("comes a few seconds after Friday opens, stays ten seconds, then slides out", async () => {
    expect(TIP_FOR_MS).toBe(10_000)
    open()
    await after(TIP_AFTER_MS - 100)
    expect(screen.queryByText(TEXT)).toBeNull()
    await after(200)
    expect(screen.getByText(TEXT)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Take me there" })).toBeTruthy()
    expect(sent).toEqual(["tip_shown"])
    await after(TIP_FOR_MS - 200)
    expect(screen.getByText(TEXT).closest("[data-leaving]")).toBeNull() // still in
    await after(300)
    expect(screen.getByText(TEXT).closest("[data-leaving]")).not.toBeNull() // sliding out
    await after(400)
    expect(screen.queryByText(TEXT)).toBeNull()
  })

  it("closes at once with ×, and says so, so that tip doesn't come back", async () => {
    open()
    await after(TIP_AFTER_MS + 100)
    expect(screen.getByText(TEXT)).toBeTruthy()
    await act(async () => screen.getByRole("button", { name: "Close tip" }).click())
    await after(400)
    expect(screen.queryByText(TEXT)).toBeNull()
    expect(sent).toEqual(["tip_shown", "tip_shown"]) // shown, then closed
  })

  it("never comes over the tour, and isn't counted then", async () => {
    open(true)
    await after(TIP_AFTER_MS + TIP_FOR_MS)
    expect(screen.queryByText(TEXT)).toBeNull()
    expect(sent).toEqual([])
  })
})
