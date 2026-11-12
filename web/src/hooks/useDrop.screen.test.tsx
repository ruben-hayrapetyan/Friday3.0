// What a finished drag does, sent to a real Friday: a block let go on the calendar is pinned there (locked with
// Shift), on a day it's due that day, on the to-do list it goes back to Friday; an event gets its new time; to-do rows
// picked together are planned one after another; a selection of empty time opens its menu, whose choices shove the
// time, draft an event there, or pin what fits.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { describe, expect, it } from "vitest"
import type { Drag } from "@/components/calendar/useDrag"
import { SelectionMenu } from "@/components/calendar/SelectionMenu"
import { Toasts } from "@/components/Toasts"
import { ShellProvider, useShell } from "@/shell/ShellContext"
import { friday, waitForSent } from "@/test/friday"
import { toMin } from "@/lib/time"
import { type Selection, useDrop } from "./useDrop"

function dayOn(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <Toasts>
        <ShellProvider today={dayOn(0)}>{children}</ShellProvider>
      </Toasts>
    </QueryClientProvider>
  )
}

const drag = (more: Partial<Drag>): Drag => ({ kind: "move", start: 0, end: 60, grab: 0, itemId: null, blockKey: null, title: "", locked: false, at: null, over: null, day: null, moved: true, x: 10, y: 20, ...more })

async function task(title: string, minutes = 60) {
  const out = await friday.c<{ result: { item: { id: number } } }>("add", { title, duration_min: minutes, due: `${dayOn(6)}T23:59` })
  return out.result.item.id
}

describe("a drop", () => {
  it("of a selection of empty time opens its menu at that time", async () => {
    const chosen: Selection[] = []
    const { result } = renderHook(() => useDrop((s) => chosen.push(s)), { wrapper })
    const at = { start: toMin(`${dayOn(1)}T14:00`), end: toMin(`${dayOn(1)}T15:30`) }
    await act(() => result.current(drag({ kind: "select", at })))
    expect(chosen).toEqual([{ start: `${dayOn(1)}T14:00`, end: `${dayOn(1)}T15:30`, x: 10, y: 20 }])
    await act(() => result.current(drag({ kind: "select", moved: false, at })))
    await act(() => result.current(drag({ kind: "select", at: null })))
    expect(chosen).toHaveLength(1) // not dragged, or off the calendar: nothing
  })

  it("of a block on the calendar pins it there, and with Shift locks it", async () => {
    const id = await task("Drop practice: pin")
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    const day = dayOn(2)
    const from = { start: toMin(`${day}T09:00`), end: toMin(`${day}T10:00`) }
    await act(() => result.current(drag({ itemId: id, title: "Drop practice: pin", blockKey: `T${id}@${day}T09:00`, ...from, over: "calendar", at: { start: toMin(`${day}T13:00`), end: toMin(`${day}T14:00`) } })))
    expect((await waitForSent("pin")).body).toEqual({ id, start: `${day}T13:00`, end: `${day}T14:00`, kind: "preferred", from_start: `${day}T09:00`, from_end: `${day}T10:00` })
    await act(() => result.current(drag({ itemId: id, title: "Drop practice: pin", ...from, locked: true, over: "calendar", at: { start: toMin(`${day}T15:00`), end: toMin(`${day}T16:00`) } })))
    const { sent } = await import("@/test/setup")
    await waitFor(() => expect(sent.filter((s) => s.name === "pin").at(-1)?.body).toMatchObject({ kind: "locked", start: `${day}T15:00` }))
  })

  it("of a to-do row on the calendar pins it at that start, its length the server's", async () => {
    const id = await task("Drop practice: row", 45)
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    const day = dayOn(3)
    await act(() => result.current(drag({ kind: "row", itemId: id, title: "Drop practice: row", over: "calendar", at: { start: toMin(`${day}T10:00`), end: toMin(`${day}T10:45`) } })))
    expect((await waitForSent("pin")).body).toEqual({ id, start: `${day}T10:00`, kind: "preferred" })
  })

  it("of a block's edge pins its new length", async () => {
    const id = await task("Drop practice: stretch", 60)
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    const day = dayOn(2)
    await act(() => result.current(drag({ kind: "resize", itemId: id, title: "Drop practice: stretch", start: toMin(`${day}T08:00`), end: toMin(`${day}T09:00`), over: "calendar", at: { start: toMin(`${day}T08:00`), end: toMin(`${day}T09:30`) } })))
    expect((await waitForSent("pin")).body).toMatchObject({ id, start: `${day}T08:00`, end: `${day}T09:30` })
  })

  it("on a whole day makes it due that day, at the end of it", async () => {
    const id = await task("Drop practice: due")
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    const day = dayOn(4)
    await act(() => result.current(drag({ itemId: id, title: "Drop practice: due", over: "day", day })))
    expect((await waitForSent("edit")).body).toEqual({ id, due: `${day}T23:59` })
    await waitFor(async () => expect((await friday.q<{ id: number; due: string }[]>("items")).find((i) => i.id === id)?.due).toBe(`${day}T23:59`))
  })

  it("on the to-do list leaves it to Friday again, but a row dropped there does nothing", async () => {
    const id = await task("Drop practice: unpin")
    const day = dayOn(2)
    await friday.c("pin", { id, start: `${day}T09:00`, end: `${day}T10:00`, kind: "preferred" })
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    await act(() => result.current(drag({ itemId: id, title: "Drop practice: unpin", over: "todo" })))
    expect((await waitForSent("unpin")).body).toEqual({ id })
    const { sent } = await import("@/test/setup")
    const before = sent.length
    await act(() => result.current(drag({ kind: "row", itemId: id, title: "Drop practice: unpin", over: "todo" })))
    await act(() => result.current(drag({ itemId: id, title: "Off the calendar", over: null })))
    expect(sent.length).toBe(before)
  })

  it("of an event gives it its new time", async () => {
    const day = dayOn(5)
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Drop practice: event", when: "fixed", start: `${day}T11:00`, end: `${day}T12:00` })
    const id = made.result.item.id
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    await act(() => result.current(drag({ event: true, itemId: id, title: "Drop practice: event", start: toMin(`${day}T11:00`), end: toMin(`${day}T12:00`), over: "calendar", at: { start: toMin(`${day}T16:00`), end: toMin(`${day}T17:00`) } })))
    expect((await waitForSent("edit")).body).toEqual({ id, start: `${day}T16:00`, end: `${day}T17:00` })
    await waitFor(async () => expect((await friday.q<{ id: number; start: string }[]>("events", { text: "Drop practice", limit: "10" })).find((i) => i.id === id)?.start).toBe(`${day}T16:00`))
  })

  it("of to-do rows picked together plans them one after another, or makes them all due on a day", async () => {
    const a = await task("Drop practice: first", 30)
    const b = await task("Drop practice: second", 60)
    const rows = [{ id: a, title: "Drop practice: first", length: 30 }, { id: b, title: "Drop practice: second", length: 60 }]
    const { result } = renderHook(() => useDrop(() => {}), { wrapper })
    const day = dayOn(3)
    await act(() => result.current(drag({ kind: "row", itemId: a, rows, over: "calendar", at: { start: toMin(`${day}T13:00`), end: toMin(`${day}T13:30`) } })))
    await waitFor(async () => {
      const { sent } = await import("@/test/setup")
      expect(sent.filter((s) => s.name === "pin").map((s) => s.body)).toEqual([
        { id: a, start: `${day}T13:00`, end: `${day}T13:30`, kind: "preferred" },
        { id: b, start: `${day}T13:30`, end: `${day}T14:30`, kind: "preferred" },
      ])
    })
    const due = dayOn(5)
    await act(() => result.current(drag({ kind: "row", itemId: a, rows, over: "day", day: due })))
    await waitFor(async () => {
      const { sent } = await import("@/test/setup")
      expect(sent.filter((s) => s.name === "edit").map((s) => s.body)).toEqual([{ id: a, due: `${due}T23:59` }, { id: b, due: `${due}T23:59` }])
    })
  })
})

describe("the menu for selected empty time", () => {
  function Shown({ selection, onShove, onClose }: { selection: Selection; onShove: (r: string) => void; onClose: () => void }) {
    const { event } = useShell()
    return (
      <>
        <SelectionMenu selection={selection} today={dayOn(0)} onShove={onShove} onClose={onClose} />
        {event && <span>Drafted {event.start}–{event.end}</span>}
      </>
    )
  }
  const day = dayOn(2)
  const selection = { start: `${day}T14:00`, end: `${day}T16:00`, x: 40, y: 40 }

  it("says the time, and shoves it", async () => {
    const shoved: string[] = []
    const user = userEvent.setup()
    render(<Shown selection={selection} onShove={(r) => shoved.push(r)} onClose={() => {}} />, { wrapper })
    expect(screen.getByText(/2pm–4pm · 2h/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Shove this time" }))
    expect(shoved).toEqual([`2pm-4pm ${day}`])
  })

  it("drafts a fixed event over it", async () => {
    const closed: number[] = []
    const user = userEvent.setup()
    render(<Shown selection={selection} onShove={() => {}} onClose={() => closed.push(1)} />, { wrapper })
    await user.click(screen.getByRole("button", { name: "Add a fixed event here" }))
    expect(screen.getByText(`Drafted ${day}T14:00–${day}T16:00`)).toBeTruthy()
    expect(closed.length).toBeGreaterThan(0)
  })

  it("shows what fits, and pins the one you pick", async () => {
    const user = userEvent.setup()
    const closed: number[] = []
    render(<Shown selection={selection} onShove={() => {}} onClose={() => closed.push(1)} />, { wrapper })
    await user.click(screen.getByRole("button", { name: "Show what fits" }))
    await waitFor(() => expect(screen.queryByText("Looking…")).toBeNull(), { timeout: 10_000 })
    const fits = await friday.q<{ item_id: number; title: string; minutes: number }[]>("fits", { minutes: "120" })
    if (!fits.length) return expect(screen.getByText("Nothing fits without something going late.")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: new RegExp(fits[0].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }))
    expect((await waitForSent("pin")).body).toMatchObject({ id: fits[0].item_id, start: `${day}T14:00`, kind: "preferred" })
    await waitFor(() => expect(closed.length).toBeGreaterThan(0))
  })

  it("closes with Escape or a click outside it", async () => {
    const closed: number[] = []
    const user = userEvent.setup()
    render(<Shown selection={selection} onShove={() => {}} onClose={() => closed.push(1)} />, { wrapper })
    await user.keyboard("{Escape}")
    expect(closed).toHaveLength(1)
    await user.click(document.body)
    expect(closed).toHaveLength(2)
  })
})
