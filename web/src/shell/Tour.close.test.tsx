// @vitest-environment happy-dom
// The tour, ended and taken again: the guide's leaving can't end the tour taken after it (the audit, 12 Nov: the tour
// ended four seconds after the last one did, whatever was showing then). The guide is a stand-in: no WebGL here.
import { act, cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ShellProvider, useShell } from "./ShellContext"
import { Tour } from "./Tour"

vi.mock("@/dialogs/walk/Guide", () => ({
  Guide: class {
    onGone: (() => void) | null = null
    resize() {}
    cue() {}
    dispose() {}
    leave() {
      setTimeout(() => this.onGone?.(), 300) // it walks off, then says it's gone
    }
  },
}))

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function Page() {
  const { tour, setTour } = useShell()
  return (
    <>
      <button onClick={() => setTour(true)}>Take the tour</button>
      {tour && <Tour />}
    </>
  )
}

describe("the tour, ended", () => {
  it("doesn't end the tour taken again soon after", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    window.innerWidth = 1440
    render(
      <MemoryRouter>
        <ShellProvider today="2026-11-12">
          <Page />
        </ShellProvider>
      </MemoryRouter>,
    )
    const tour = () => screen.queryByRole("dialog", { name: /^Tour of Friday/ })
    act(() => screen.getByRole("button", { name: "Take the tour" }).click())
    await act(async () => void (await vi.dynamicImportSettled())) // the guide is in
    act(() => screen.getByRole("button", { name: "End the tour" }).click())
    await act(async () => void vi.advanceTimersByTime(400)) // the guide has gone, and the tour with it
    expect(tour()).toBeNull()
    act(() => screen.getByRole("button", { name: "Take the tour" }).click())
    expect(tour()).not.toBeNull()
    await act(async () => void vi.advanceTimersByTime(4000))
    expect(tour()).not.toBeNull()
  })
})
