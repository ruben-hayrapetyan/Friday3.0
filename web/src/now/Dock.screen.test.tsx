// The Now bar over Alex's weeks: timing something (Done, Pause, Do something else, alongside, More, Forgot to
// stop?), in a block, in a class, free (what to start, a nap, a snack), and the sleep and meal taps. What the server
// says is on depends on the hour the test runs at, so the tests that need a block, a class or free time say so to the
// page themselves (the `now` the server would answer then); what's timed, napped or eaten is the server's own.
import { cleanup, screen, waitFor, within } from "@testing-library/react"
import type { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { addDays } from "@/lib/time"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Now = Schemas["NowOut"]
type Block = Schemas["BlockOut"]

const dock = () => document.querySelector<HTMLElement>('[data-tour="now"]') as HTMLElement
const inDock = () => within(dock())
const calendar = () => friday.q<Schemas["CalendarOut"]>("calendar", { start: "2026-01-01", days: "1" })
const at = (local: string, minutes: number) => new Date(Date.parse(`${local}:00Z`) + minutes * 60_000).toISOString().slice(0, 16)

/** Two of Alex's assignments a week on, to time. */
async function work(): Promise<Block[]> {
  const first = addDays((await calendar()).today, 4)
  const plan = await friday.q<Schemas["PlanOut"]>("plan", { start: `${first}T00:00`, end: `${addDays(first, 7)}T00:00` })
  const seen = new Set<number>()
  return plan.blocks.filter((b) => b.preset === "Assignment" && !seen.has(b.item_id) && seen.add(b.item_id))
}

/** The bar, once it shows. */
async function openDock(route = "/") {
  cleanup() // the page opened before, if any
  const opened = await openFriday(route)
  await waitFor(() => expect(dock()).not.toBeNull(), { timeout: 10_000 })
  return opened
}

/** The page told what's on now, as the server would say it at another hour. */
async function sayNow(client: QueryClient, change: (now: Now, local: string) => Partial<Now>) {
  await waitFor(() => expect(client.getQueryData(["now"])).toBeTruthy())
  await waitFor(() => expect(client.isFetching()).toBe(0)) // nothing on its way to say otherwise
  const local = (await calendar()).now
  client.setQueryData<Now>(["now"], (was) => was && { ...was, ...change(was, local) })
}

/** The nap or meal just tapped taken away again (begun this minute, it can't be ended yet). */
async function nappedNone() {
  await waitFor(async () => expect((await friday.q<Schemas["SleepOut"]>("sleep")).napping).not.toBeNull())
  const nap = (await friday.q<Schemas["SleepOut"]>("sleep")).napping
  if (nap) await friday.c("nap_remove", { id: nap.id })
}
async function eatenNone() {
  await waitFor(async () => expect((await friday.q<Schemas["MealsOut"]>("meals")).eating).not.toBeNull())
  const meal = (await friday.q<Schemas["MealsOut"]>("meals")).eating
  if (meal) await friday.c("meal_remove", { id: meal.id })
}

async function setting(key: string, value: Record<string, unknown>) {
  const settings = await friday.q<Record<string, Record<string, unknown>>>("settings")
  await friday.c("settings_set", { key, value: { ...settings[key], ...value } })
}

describe("timing something", () => {
  it("ticks, says what's next, and stops with Done or Pause", async () => {
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    const { user } = await openDock()
    expect(await inDock().findByText(a.title)).toBeTruthy()
    expect(inDock().getByText(/^Timing since /)).toBeTruthy()
    expect(inDock().getByText(/then /)).toBeTruthy()
    await user.click(inDock().getByRole("button", { name: "Pause the timer (Space)" }))
    expect((await waitForSent("stop")).body).toEqual({})
    // the pause has landed before the timer starts again: sent isn't done, and a stop landing after the start
    // left no timer on a busy machine (13 Nov)
    await waitFor(async () => expect((await friday.q<{ timer: unknown }>("status")).timer).toBeNull(), { timeout: 10_000 })
    await friday.c("start", { id: a.item_id })
    await waitFor(async () => expect((await friday.q<{ timer: unknown }>("status")).timer).toBeTruthy())
    cleanup() // the first page gone, so the bar read is the new one's
    const { user: again } = await openDock()
    await again.click(await inDock().findByTitle("Stop the timer and mark it done", {}, { timeout: 20_000 }))
    expect((await waitForSent("stop")).body).toEqual({ done: true })
    await friday.c("reopen", { id: a.item_id })
  })

  it("switches to something else, or starts it alongside, and stops what's alongside", async () => {
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    const { user } = await openDock()
    const swap = await inDock().findByRole("button", { name: "Do something else" })
    await user.click(swap)
    const instead = await inDock().findByText(/^Instead, with nothing going late:|^Nothing else fits right now/)
    const plus = inDock().queryAllByRole("button", { name: /alongside$/ })
    if (plus.length) {
      await user.click(plus[0])
      const started = (await waitForSent("start")).body as { id: number; alongside: boolean }
      expect(started.alongside).toBe(true)
      // what was timed goes on beside it: a row of its own, ticking, with Done and Stop
      await waitFor(() => expect(screen.getByTestId("alongside").textContent).toMatch(/Also timing/))
      const row = within(screen.getByTestId("alongside"))
      expect(await row.findByText(a.title)).toBeTruthy()
      await user.click(row.getByRole("button", { name: new RegExp(`^Stop timing `) }))
      expect((await waitForSent("stop")).body).toEqual({ id: a.item_id })
      await friday.c("start", { id: a.item_id, alongside: true })
      const { user: again } = await openDock()
      const done = await within(await screen.findByTestId("alongside", {}, { timeout: 5000 })).findByRole("button", { name: /^Done: stop it and mark/ })
      await again.click(done)
      expect((await waitForSent("stop")).body).toEqual({ id: started.id, done: true })
      await friday.c("reopen", { id: started.id })
      await again.click(await inDock().findByRole("button", { name: "Do something else" }))
      const chip = inDock().getAllByRole("button").find((b) => b.getAttribute("title") === "Switch to it: what you're on stops") as HTMLElement
      await again.click(chip)
      expect((await waitForSent("start")).body).toMatchObject({ id: expect.any(Number) })
    } else {
      expect(instead.textContent).toMatch(/Nothing else fits/)
    }
    await friday.c("stop", {})
  })

  it("offers More: switch, stuck, shove, pace and the task's detail", async () => {
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    const { user } = await openDock()
    const more = await inDock().findByRole("button", { name: "More" })
    await user.click(more)
    for (const option of ["Switch", "Stuck", "Shove", "Pace", "Open"]) expect(inDock().getByRole("button", { name: new RegExp(`^${option}`) })).toBeTruthy()
    await user.click(inDock().getByRole("button", { name: /^Switch/ }))
    expect(await inDock().findByText(/^Instead, with nothing going late:|^Nothing else fits right now/)).toBeTruthy()
    await user.click(inDock().getByRole("button", { name: "More" }))
    await user.click(inDock().getByRole("button", { name: /^Stuck/ }))
    expect((await waitForSent("stuck")).body).toEqual({ id: a.item_id })
    await user.click(inDock().getByRole("button", { name: "More" }))
    await user.click(inDock().getByRole("button", { name: /^Pace/ }))
    expect(await screen.findByText(/Easy/)).toBeTruthy()
    await user.keyboard("{Escape}")
    await user.click(inDock().getByRole("button", { name: "More" }))
    await user.click(inDock().getByRole("button", { name: /^Shove/ }))
    await user.keyboard("{Escape}")
    await user.click(inDock().getByRole("button", { name: "More" }))
    await user.click(inDock().getByRole("button", { name: /^Open/ }))
    await waitFor(() => expect(window.location.hash).toBe(`#/todo?item=${a.item_id}`))
    await friday.c("stop", {})
  })

  it("stops a timer left running as of when you really stopped", async () => {
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    const { user } = await openDock()
    await user.click(await inDock().findByRole("button", { name: "Forgot to stop?" }))
    const group = inDock().getByRole("group", { name: "When you stopped" })
    await user.click(within(group).getByRole("button", { name: "Cancel" }))
    expect(inDock().queryByRole("group", { name: "When you stopped" })).toBeNull()
    await user.click(inDock().getByRole("button", { name: "Forgot to stop?" }))
    await user.click(within(inDock().getByRole("group", { name: "When you stopped" })).getByRole("button", { name: "Stop then" }))
    const stop = (await waitForSent("stop")).body as { at: string; done: boolean }
    expect(stop.done).toBe(false)
    expect(stop.at).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/)
    await friday.c("start", { id: a.item_id })
    const { user: again } = await openDock()
    await again.click(await inDock().findByRole("button", { name: "Forgot to stop?" }))
    await again.click(within(inDock().getByRole("group", { name: "When you stopped" })).getByRole("button", { name: "Done then" }))
    expect((await waitForSent("stop")).body).toMatchObject({ done: true })
    await friday.c("reopen", { id: a.item_id })
  })

  it("draws a smaller bar in the minimal style", async () => {
    window.localStorage.setItem("friday-look-v8", JSON.stringify({ dockStyle: "Minimal" }))
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    await openDock()
    const done = await inDock().findByTitle("Stop the timer and mark it done")
    expect(done.textContent).toBe("")
    await friday.c("stop", {})
  })
})

describe("between timers", () => {
  it("in a planned block: Start, or Resume with some done, and Done", async () => {
    const [a, b] = await work()
    const { user, client } = await openDock()
    await sayNow(client, (_, local) => ({ current: { ...a, start: at(local, -10), end: at(local, 50) }, current_source: "block" }))
    expect(await inDock().findByText(a.title)).toBeTruthy()
    expect(inDock().getByText(/^Now /)).toBeTruthy()
    expect(inDock().getByText(/ left$/)).toBeTruthy()
    await user.click(inDock().getByTitle(/^(Start|Resume) the timer/))
    expect((await waitForSent("start")).body).toEqual({ id: a.item_id })
    await friday.c("stop", {})
    await sayNow(client, (_, local) => ({ current: { ...b, start: at(local, -10), end: at(local, 50) }, current_source: "block" }))
    await user.click(await inDock().findByRole("button", { name: "Mark it done" }))
    expect((await waitForSent("done")).body).toEqual({ id: b.item_id })
    await friday.c("reopen", { id: b.item_id })
  })

  it("says Resume, with how much is done, for work already begun", async () => {
    const items = await friday.q<Schemas["ItemOut"][]>("items")
    const begun = items.find((i) => i.when !== "fixed" && i.done_min > 0) as Schemas["ItemOut"]
    const [a] = await work()
    const { client } = await openDock()
    await sayNow(client, (_, local) => ({ current: { ...a, item_id: begun.id, title: begun.title, start: at(local, -10), end: at(local, 50) }, current_source: "block" }))
    await waitFor(() => expect(inDock().getByTitle(/^Resume the timer: .* done so far/).textContent).toMatch("Resume"))
  })

  it("in a class: the class, until when, and what's after", async () => {
    const { client } = await openDock()
    const first = addDays((await calendar()).today, 4)
    const plan = await friday.q<Schemas["PlanOut"]>("plan", { start: `${first}T00:00`, end: `${addDays(first, 7)}T00:00` })
    const lecture = plan.fixed.find((f) => f.title === "MATH 1910 Lecture") as Schemas["ItemOut"]
    await sayNow(client, (_, local) => ({
      current: { key: `F${lecture.id}`, item_id: lecture.id, title: lecture.title, area: lecture.area, preset: lecture.preset, estimated: false, start: at(local, -20), end: at(local, 30), pinned: null, tentative: false, fixed: true, cost: {}, state: null, background: false },
      current_source: "event",
    }))
    expect(await inDock().findByText("MATH 1910 Lecture")).toBeTruthy()
    expect(inDock().getByText(/^Now, until /)).toBeTruthy()
    expect(inDock().queryByRole("button", { name: "More" })).toBeNull()
  })

  it("free: how long, what's next, and what to start, one tap each", async () => {
    const { user, client } = await openDock()
    await sayNow(client, (was, local) => ({
      current: null,
      current_source: "free",
      next: was.next ?? null,
      gap_minutes: 95,
      fits: [
        { item_id: 566, title: "MATH 1910 Written HW 8", minutes: 95, price: 250, slack_hours: 40 },
        { item_id: 569, title: "CHEM 2090 lab report 6", minutes: 95, price: 250, slack_hours: 180 },
      ],
      ...(was.next ? {} : { next: { key: "T1@x", item_id: 1, title: "Breakfast", area: null, preset: "Routine", estimated: false, start: at(local, 95), end: at(local, 125), pinned: null, tentative: false, fixed: false, cost: {}, state: null, background: false } }),
    }))
    expect(await inDock().findByText(/^Free until /)).toBeTruthy()
    expect(inDock().getByText("Start now:")).toBeTruthy()
    await user.click(inDock().getByRole("button", { name: /^CHEM 2090 lab report 6/ }))
    expect((await waitForSent("start")).body).toEqual({ id: 569 })
    await friday.c("stop", {})
    await sayNow(client, () => ({ current: null, current_source: "free", next: null, gap_minutes: 0, fits: [] }))
    expect(await inDock().findByText("Free for the rest of today")).toBeTruthy()
    expect(inDock().getByText("Nothing needs this time. It's yours.")).toBeTruthy()
  })
})

describe("sleep and meals, tracked", () => {
  it("offers a nap and a snack when free, and says so while napping or eating, until you're done", async () => {
    await setting("sleep_tracking", { on: true })
    await setting("meal_tracking", { on: true })
    const { user, client } = await openDock()
    await sayNow(client, () => ({ current: null, current_source: "free", next: null, gap_minutes: 0, fits: [] }))
    await user.click(await inDock().findByRole("button", { name: /^Snack/ }))
    expect((await waitForSent("meal_start")).body).toEqual({ kind: "snack" })
    await eatenNone()
    await sayNow(client, () => ({ current: null, current_source: "free", next: null, gap_minutes: 0, fits: [] }))
    await user.click(await inDock().findByRole("button", { name: /^Nap/ }))
    expect((await waitForSent("nap_start")).body).toEqual({})
    expect(await inDock().findByText(/^Napping since /)).toBeTruthy()
    await nappedNone()
    // begun a while ago: the bar says since when, and ends it
    const now = (await calendar()).now
    await friday.c("nap_start", { at: at(now, -30) })
    const { user: again } = await openDock()
    expect(await inDock().findByText(/^Napping since /)).toBeTruthy()
    await again.click(inDock().getByRole("button", { name: "I'm up" }))
    expect(await waitForSent("nap_end")).toBeTruthy()
    await waitFor(async () => expect((await friday.q<Schemas["SleepOut"]>("sleep")).napping).toBeNull())
    await friday.c("meal_start", { kind: "snack", at: at(now, -20) })
    await openDock()
    await again.click(await inDock().findByRole("button", { name: "Done eating" }))
    expect(await waitForSent("meal_end")).toBeTruthy()
    await waitFor(async () => expect((await friday.q<Schemas["MealsOut"]>("meals")).eating).toBeNull())
  })

  it("pauses the timer first for a nap from More", async () => {
    const [a] = await work()
    await friday.c("start", { id: a.item_id })
    const { user } = await openDock()
    await user.click(await inDock().findByRole("button", { name: "More" }))
    await user.click(await inDock().findByRole("button", { name: /^Nap/ }))
    expect((await waitForSent("stop")).body).toEqual({})
    expect(await waitForSent("nap_start")).toBeTruthy()
    await nappedNone()
    await friday.c("start", { id: a.item_id })
    const { user: again } = await openDock()
    await again.click(await inDock().findByRole("button", { name: "More" }))
    await again.click(await inDock().findByRole("button", { name: /^Snack/ }))
    expect((await waitForSent("meal_start")).body).toEqual({ kind: "snack" })
    await eatenNone()
    await friday.c("stop", {})
  })

  it("offers the sleep tap that fits the hour", async () => {
    const { user, client } = await openDock()
    // a tap waits for the one before it to be saved
    const press = async (name: string) => {
      const button = await inDock().findByRole("button", { name })
      await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
      await user.click(button)
    }
    const tap = async (next: "up" | "ready" | "done" | "bed") => {
      await waitFor(() => expect(client.getQueryData(["sleep"])).toBeTruthy())
      await waitFor(() => expect(client.isFetching()).toBe(0))
      client.setQueryData<Schemas["SleepOut"]>(["sleep"], (s) => s && { ...s, on: true, napping: null, next })
    }
    await tap("up")
    expect(await inDock().findByText("Just up?")).toBeTruthy()
    await press("I'm up")
    expect((await waitForSent("sleep_mark")).body).toEqual({ kind: "up" })
    await tap("ready")
    await press("Ready to work")
    expect((await waitForSent("sleep_mark")).body).toEqual({ kind: "ready" })
    await tap("done")
    expect(await inDock().findByText("Done with work for the night?")).toBeTruthy()
    await press("Going to bed")
    expect((await waitForSent("sleep_mark")).body).toEqual({ kind: "bed" })
    await tap("done")
    await press("Done with work")
    expect((await waitForSent("sleep_mark")).body).toEqual({ kind: "done" })
    await tap("bed")
    expect(await inDock().findByText("Heading to sleep?")).toBeTruthy()
  })

  it("asks about a meal at its time: eating now, or skip it; and another of the last one", async () => {
    const { user, client } = await openDock()
    const meal = async (change: Partial<Schemas["MealsOut"]>) => {
      await waitFor(() => expect(client.getQueryData(["meals"])).toBeTruthy())
      await waitFor(() => expect(client.isFetching()).toBe(0))
      client.setQueryData<Schemas["MealsOut"]>(["meals"], (m) => m && { ...m, on: true, eating: null, ...change })
    }
    await meal({ next: "lunch" })
    expect(await inDock().findByText("Lunch?")).toBeTruthy()
    await user.click(inDock().getByRole("button", { name: "Skip" }))
    expect((await waitForSent("meal_skip")).body).toEqual({ kind: "lunch" })
    await meal({ next: "dinner" })
    await user.click(await inDock().findByRole("button", { name: "Eating now" }))
    expect((await waitForSent("meal_start")).body).toEqual({ kind: "dinner" })
    await eatenNone()
    await sayNow(client, () => ({ current: null, current_source: "free", next: null, gap_minutes: 0, fits: [] }))
    await meal({ next: null, again: "dinner" })
    await user.click(await inDock().findByRole("button", { name: /^Another dinner/ }))
    expect((await waitForSent("meal_start")).body).toEqual({ kind: "dinner" })
  })

  it("draws a meal you're eating on the calendar, opening Insights → Meals", async () => {
    const now = (await calendar()).now
    await friday.c("meal_log", { kind: "snack", start: at(now, -60), end: at(now, -25) })
    const { user } = await openDock()
    const eaten = await waitFor(
      () => {
        const found = document.querySelector<HTMLElement>('[data-block-key^="M"]')
        expect(found).not.toBeNull()
        return found as HTMLElement
      },
      { timeout: 10_000 },
    )
    await user.click(eaten)
    await waitFor(() => expect(window.location.hash).toBe("#/insights?tab=meals"))
  })
})
