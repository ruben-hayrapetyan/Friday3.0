// A block's card (BlockPopover) over Alex's weeks: what it is and why it's there, and everything it does to the
// block (start, pause, done, pin, unlock, tentative, skip, delete, try elsewhere, history), to an event (going or
// working through it, the task its time is for, its category, repeating, editing), to time you shoved, and to the
// past (a sitting's times, work counted done). Each test opens the card a week ahead, where every block is to come.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { addDays } from "@/lib/time"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"

type Plan = Schemas["PlanOut"]
type Block = Schemas["BlockOut"]
type Item = Schemas["ItemOut"]

const today = async () => (await friday.q<Schemas["CalendarOut"]>("calendar", { start: "2026-01-01", days: "1" })).today

async function settled() {
  const until = Date.now() + 60_000
  for (;;) {
    const s = await friday.q<Schemas["StatusOut"]>("status")
    if (s.plan_generation === s.generation || Date.now() > until) return s
    await new Promise((r) => setTimeout(r, 400))
  }
}

/** Friday's timer on `id`, or on nothing, as the server has it. */
async function timerIs(id: number | null) {
  await waitFor(async () => expect((await friday.q<Schemas["StatusOut"]>("status")).timer?.item_id ?? null).toBe(id), { timeout: 10_000 })
}

/** The plan from today to the end of the two weeks, once Friday has finished replanning. */
async function nextWeek(): Promise<Plan> {
  await settled()
  const first = await today()
  for (let tries = 0; ; tries++) {
    const plan = await friday.q<Plan>("plan", { start: `${first}T00:00`, end: `${addDays(first, 14)}T00:00` })
    if (plan.blocks || tries > 10) return plan // asked mid-replan, it can answer with an error: ask again
    await new Promise((r) => setTimeout(r, 500))
  }
}

/** A block still to come, one per task, by what it is. */
async function blockOf(test: (b: Block) => boolean, skip = 0): Promise<Block> {
  const seen = new Set<number>()
  const found = (await nextWeek()).blocks.filter((b) => b.key.startsWith("T") && !b.state && test(b) && !seen.has(b.item_id) && seen.add(b.item_id))
  return found[skip] ?? found[0]
}
const assignment = (b: Block) => b.preset === "Assignment"

const box = (key: string) => document.querySelector<HTMLElement>(`[data-block-key="${CSS.escape(key)}"]`)
const card = () => document.querySelector<HTMLElement>("aside.fr-block-card")
const inCard = () => within(card() as HTMLElement)

/** The plan at the week of `at` (a block or an event), with its card open; the page opened before is closed. */
async function openCard(at: { key: string; start: string } | Block) {
  const key = at.key
  cleanup()
  const opened = await openFriday("/")
  const ahead = Math.floor((Date.parse(`${at.start.slice(0, 10)}T00:00:00Z`) - Date.parse(`${await today()}T00:00:00Z`) + 3 * 86_400_000) / (7 * 86_400_000))
  for (let n = 0; n < ahead; n++) await opened.user.click(screen.getByRole("button", { name: "Next" }))
  await waitFor(() => expect(box(key)).not.toBeNull(), { timeout: 15_000 })
  await opened.user.click(box(key) as HTMLElement)
  await detailed()
  return opened
}

/** The card, once its item's detail has come (its facts show). */
async function detailed() {
  await waitFor(() => expect(card()?.textContent).toMatch(/Deadline|Calendar/), { timeout: 10_000 })
}

/** An event's card key and time. */
const ofEvent = (e: Item) => ({ key: `F${e.id}`, start: e.start as string })

/** The block of item `id` a week on, wherever the plan has it now. */
const blockFor = (id: number) => blockOf((b) => b.item_id === id)

describe("a planned block's card", () => {
  it("says what it is, when, why there, and what's left", async () => {
    const block = await blockOf(assignment)
    await openCard(block)
    expect(inCard().getByText(block.title)).toBeTruthy()
    expect(inCard().getByText("Planned · Friday decides")).toBeTruthy()
    expect(await inCard().findByText("Why this time")).toBeTruthy()
    for (const fact of ["Due", "Deadline"]) expect(inCard().getByText(fact)).toBeTruthy()
    expect(inCard().getByText("Hard deadline")).toBeTruthy()
    expect(inCard().getByText("Double-click its time on the calendar to type a new one")).toBeTruthy()
  })

  it("starts the timer on it, then pauses it or finishes it from the card", async () => {
    const block = await blockOf(assignment)
    const { user } = await openCard(block)
    await user.click(inCard().getByRole("button", { name: /^(Start|Resume)/ }))
    expect((await waitForSent("start")).body).toEqual({ id: block.item_id })
    expect(card()).not.toBeNull() // the card stays open (12 Nov)
    await openCard(await blockFor(block.item_id))
    await user.click(await inCard().findByRole("button", { name: /^Pause/ }, { timeout: 10_000 }))
    expect((await waitForSent("stop")).body).toEqual({ id: block.item_id })
    await timerIs(null) // the pause has landed before the timer starts again
    await friday.c("start", { id: block.item_id })
    await timerIs(block.item_id)
    await openCard(await blockFor(block.item_id))
    await inCard().findByRole("button", { name: /^Pause/ }, { timeout: 10_000 }) // the card knows it's being timed
    await user.click(await inCard().findByRole("button", { name: /^Done/ }))
    expect((await waitForSent("stop")).body).toEqual({ id: block.item_id, done: true })
    await friday.c("reopen", { id: block.item_id })
  })

  it("switches to it from what's being timed, or times it alongside", async () => {
    const running = await blockOf(assignment, 1)
    await friday.c("start", { id: running.item_id })
    const block = await blockOf(assignment, 2)
    const { user } = await openCard(block)
    const switching = await inCard().findByRole("button", { name: /^Switch/ })
    expect(switching.getAttribute("title")).toMatch(/stops$/)
    await user.click(inCard().getByRole("button", { name: /^Alongside/ }))
    expect((await waitForSent("start")).body).toEqual({ id: block.item_id, alongside: true })
    await friday.c("stop", { id: block.item_id })
    await openCard(await blockFor(block.item_id))
    await user.click(await inCard().findByRole("button", { name: /^Switch/ }))
    expect((await waitForSent("start")).body).toEqual({ id: block.item_id })
    await friday.c("stop", {})
  })

  it("ticks it off with Done", async () => {
    const block = await blockOf(assignment, 3)
    const { user } = await openCard(block)
    await user.click(inCard().getByRole("button", { name: /^Done\s*Ticks it off/ }))
    expect((await waitForSent("done")).body).toEqual({ id: block.item_id })
    await friday.c("reopen", { id: block.item_id })
  })

  it("pins it where it is, then lets Friday decide again", async () => {
    const block = await blockOf(assignment)
    const { user } = await openCard(block)
    await user.click(inCard().getByRole("button", { name: "Pin here" }))
    expect((await waitForSent("pin")).body).toEqual({ id: block.item_id, start: block.start, end: block.end, kind: "preferred", from_start: block.start, from_end: block.end })
    const pinned = await blockOf((b) => b.item_id === block.item_id && b.pinned === "preferred")
    await openCard(pinned)
    expect(inCard().getByText("Pinned here · resists moving")).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Unpin" }))
    expect((await waitForSent("unpin")).body).toEqual({ id: block.item_id })
  })

  it("unlocks a locked block, leaving it pinned there", async () => {
    const block = await blockOf(assignment, 1)
    await friday.c("pin", { id: block.item_id, start: block.start, end: block.end, kind: "locked", from_start: block.start, from_end: block.end })
    const locked = await blockOf((b) => b.item_id === block.item_id && b.pinned === "locked")
    const { user } = await openCard(locked)
    expect(inCard().getByText("Locked · won’t move")).toBeTruthy()
    expect(inCard().queryByRole("button", { name: "Pin here" })).toBeNull()
    await user.click(inCard().getByRole("button", { name: "Unlock" }))
    expect((await waitForSent("pin")).body).toMatchObject({ id: block.item_id, kind: "preferred" })
    await friday.c("unpin", { id: block.item_id })
  })

  it("plans it loosely when it might not happen, and as usual again", async () => {
    const block = await blockOf(assignment, 2)
    const { user } = await openCard(block)
    await user.click(await inCard().findByRole("button", { name: "Might not happen" }))
    expect((await waitForSent("edit")).body).toEqual({ id: block.item_id, certainty: "tentative" })
    await openCard(await blockFor(block.item_id))
    await user.click(await inCard().findByRole("button", { name: "It will happen" }))
    expect((await waitForSent("edit")).body).toEqual({ id: block.item_id, certainty: "planned" })
  })

  it("finds the cheapest other place for it and moves it there, and shows its history", async () => {
    const block = await blockOf(assignment)
    const { user } = await openCard(block)
    await user.click(inCard().getByRole("button", { name: "History" }))
    expect(inCard().getByRole("button", { name: "History" }).getAttribute("aria-expanded")).toBe("true")
    // what was done to it, by whom
    await waitFor(() => expect(inCard().queryAllByText(/· (You|Friday)/).length + inCard().queryAllByText("Nothing yet.").length).toBeGreaterThan(0))
    await user.click(inCard().getByRole("button", { name: "Try elsewhere" }))
    await waitFor(() => expect(inCard().queryByText("Looking for the cheapest other place…")).toBeNull(), { timeout: 20_000 })
    const move = inCard().queryByRole("button", { name: "Move there" })
    if (move) {
      expect(inCard().getByText(/costs (no more|[\d.]+ points more)/)).toBeTruthy()
      await user.click(move)
      expect((await waitForSent("pin")).body).toMatchObject({ id: block.item_id, kind: "preferred", from_start: block.start })
      expect(card()).toBeNull()
    } else {
      expect(inCard().getByText(/^Nowhere else/)).toBeTruthy()
    }
  })

  it("deletes it from the card, or with Delete", async () => {
    const day = addDays(await today(), 6)
    for (const title of ["Return library books", "Email the TA"]) {
      await friday.c("add", { title, when: "window", release: `${day}T00:00`, due: `${day}T23:00`, amount: "fixed", duration_min: 30 })
    }
    const first = await blockOf((b) => b.title === "Return library books")
    const { user } = await openCard(first)
    await user.click(inCard().getByRole("button", { name: "Delete" }))
    expect((await waitForSent("drop")).body).toEqual({ id: first.item_id })
    const second = await blockOf((b) => b.title === "Email the TA")
    await openCard(second)
    await user.keyboard("{Delete}")
    expect((await waitForSent("drop")).body).toEqual({ id: second.item_id })
    await waitFor(() => expect(card()).toBeNull())
  })
})

describe("a repeating block's card", () => {
  it("skips one occurrence, and asks which when it's deleted", async () => {
    const meal = await blockOf((b) => b.title === "Lunch")
    const { user } = await openCard(meal)
    expect(await inCard().findByText(/^Repeats/)).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Skip this one" }))
    expect((await waitForSent("skip")).body).toEqual({ id: meal.item_id })
    const another = await blockOf((b) => b.title === "Lunch", 1)
    await openCard(another)
    await inCard().findByRole("button", { name: "Skip this one" })
    await user.click(inCard().getByRole("button", { name: "Delete" }))
    expect(inCard().getByRole("button", { name: "Every one" })).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Just this one" }))
    expect((await waitForSent("skip")).body).toEqual({ id: another.item_id })
  })

  it("deletes every one of a series when asked by Backspace", async () => {
    const chore = await blockOf((b) => b.title === "Laundry")
    const { user } = await openCard(chore)
    await waitFor(() => expect(inCard().getByText(/^Repeats/)).toBeTruthy())
    await user.keyboard("{Backspace}")
    await user.click(await inCard().findByRole("button", { name: "Every one" }))
    expect(await waitForSent("series_delete")).toBeTruthy()
  })
})

describe("an event's card", () => {
  const lecture = async (title = "MATH 1910 Lecture", n = 0) => (await nextWeek()).fixed.filter((f) => f.title === title)[n] as Item

  it("says its calendar, colour and category, and that it repeats", async () => {
    const event = await lecture()
    await openCard(ofEvent(event))
    expect(inCard().getByText("Fixed time")).toBeTruthy()
    expect(inCard().getAllByText("Cornell Classes").length).toBeGreaterThan(0)
    for (const fact of ["Calendar", "Colour", "Notes", "Category"]) expect(inCard().getByText(fact)).toBeTruthy()
    expect(await inCard().findByText(/^Repeats/)).toBeTruthy()
    expect((await inCard().findByRole("radio", { name: /^I'm going/ }, { timeout: 5000 })).getAttribute("aria-checked")).toBe("true")
  })

  it("changes its category from the card", async () => {
    const event = await lecture()
    const { user } = await openCard(ofEvent(event))
    await user.click(inCard().getByRole("button", { name: `Category of ${event.title}` }))
    const options = screen.getAllByRole("option")
    const other = options.find((o) => o.getAttribute("aria-selected") !== "true" && o.textContent !== "None") as HTMLElement
    await user.click(other)
    expect((await waitForSent("event_category")).body).toEqual({ id: event.id, category: other.textContent })
  })

  it("is worked through, its time for any work or a to-do first, and gone to again", async () => {
    const event = await lecture("ENGL 1170 Seminar")
    const { user } = await openCard(ofEvent(event))
    await user.click(await inCard().findByRole("radio", { name: /^Work through it/ }, { timeout: 5000 }))
    expect((await waitForSent("event_choice")).body).toEqual({ id: event.id, choice: "through" })
    expect(inCard().getByRole("radio", { name: /^Work through it/ }).getAttribute("aria-checked")).toBe("true")
    expect(inCard().getByText("Any work Friday picks.")).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Pick a to-do" }))
    const find = inCard().getByRole("textbox", { name: "Find a task" })
    await user.type(find, "no such task anywhere")
    expect(inCard().getByText("No task by that name.")).toBeTruthy()
    await user.clear(find)
    await user.type(find, "CHEM")
    // the event comes back worked through meanwhile and the card redraws: the pick is made on the list as it is then
    await waitFor(
      async () => {
        const task = inCard().queryAllByRole("button").find((b) => /^CHEM 2090 lab report/.test(b.textContent ?? ""))
        if (!sent.some((c) => c.name === "event_hold") && task) await user.click(task)
        await waitForSent("event_hold", 300)
      },
      { timeout: 10_000 },
    )
    expect((await waitForSent("event_hold")).body).toMatchObject({ id: event.id, task_id: expect.any(Number) })
    expect(inCard().getByText(/^Time for CHEM 2090 lab report/)).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Change" }))
    await user.click(inCard().getByRole("button", { name: "Cancel" }))
    await user.click(inCard().getByRole("button", { name: "Any work" }))
    expect((await waitForSent("event_hold")).body).toEqual({ id: event.id })
    // worked through still: going again puts its time back
    await settled()
    await openCard(ofEvent(event))
    await waitFor(() => expect(inCard().getByRole("radio", { name: /^Work through it/ }).getAttribute("aria-checked")).toBe("true"))
    await user.click(inCard().getByRole("radio", { name: /^I'm going/ }))
    expect((await waitForSent("event_choice")).body).toEqual({ id: event.id, choice: "going" })
    expect(inCard().getByRole("radio", { name: /^I'm going/ }).getAttribute("aria-checked")).toBe("true") // still open
  })

  it("is skipped: not going, crossed out, its time free; not the same as working through it", async () => {
    const event = await lecture("ENGL 1170 Seminar", 1)
    const { user } = await openCard(ofEvent(event))
    await user.click(await inCard().findByRole("radio", { name: /^Skip it/ }, { timeout: 5000 }))
    expect((await waitForSent("event_choice")).body).toEqual({ id: event.id, choice: "skip" })
    // the card stays open on its new choice (12 Nov: "when i hit skip it, the sidebar shouldn't close")
    expect(inCard().getByRole("radio", { name: /^Skip it/ }).getAttribute("aria-checked")).toBe("true")
    await waitFor(async () => expect(((await friday.q("item", { id: String(event.id) })) as { item: Item }).item.left_out).toBe("skipped"))
    await settled()
    await openCard(ofEvent(event))
    await waitFor(() => expect(inCard().getByRole("radio", { name: /^Skip it/ }).getAttribute("aria-checked")).toBe("true"))
    expect(inCard().getByRole("radio", { name: /^Work through it/ }).getAttribute("aria-checked")).toBe("false")
  })

  it("goes back to what it was when Friday refuses the choice", async () => {
    // the audit, 12 Nov: Skip it stayed chosen on the card after the server said no, though nothing had changed
    const event = await lecture("ENGL 1170 Seminar", 2)
    const { user } = await openCard(ofEvent(event))
    const going = await inCard().findByRole("radio", { name: /^I'm going/ }, { timeout: 5000 })
    expect(going.getAttribute("aria-checked")).toBe("true")
    const real = window.fetch
    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes("/api/c/event_choice") ? new Response(JSON.stringify({ message: "Friday couldn't save that" }), { status: 500 }) : real(input, init)) as typeof fetch
    try {
      await user.click(inCard().getByRole("radio", { name: /^Skip it/ }))
      expect(await screen.findByText("Friday couldn't save that")).toBeTruthy()
      await waitFor(() => expect(inCard().getByRole("radio", { name: /^I'm going/ }).getAttribute("aria-checked")).toBe("true"))
      expect(inCard().getByRole("radio", { name: /^Skip it/ }).getAttribute("aria-checked")).toBe("false")
    } finally {
      window.fetch = real
    }
  })

  it("asks whether an event's time is for the task its name suggests", async () => {
    const day = addDays(await today(), 5)
    await friday.c("add", { title: "CHEM 2090 lab report 6 writing time", when: "fixed", start: `${day}T16:30`, end: `${day}T17:30` })
    const event = (await nextWeek()).fixed.find((f) => f.title === "CHEM 2090 lab report 6 writing time") as Item
    const { user } = await openCard(ofEvent(event))
    expect(await inCard().findByText(/^Is this time for CHEM 2090 lab report 6\?/)).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Yes" }))
    expect((await waitForSent("event_hold")).body).toMatchObject({ id: event.id, task_id: expect.any(Number) })
    // held: once the event comes back with it, the card says whose time it is
    expect(await inCard().findByText("Time for CHEM 2090 lab report 6", {}, { timeout: 10_000 })).toBeTruthy()
    await user.click(inCard().getByRole("button", { name: "Free it" }))
    expect((await waitForSent("event_hold")).body).toEqual({ id: event.id })
  })

  it("makes an event of your own repeat, and opens it in the drawer to edit", async () => {
    const day = addDays(await today(), 5)
    await friday.c("add", { title: "Coffee with Priya", when: "fixed", start: `${day}T15:00`, end: `${day}T15:45` })
    const event = (await nextWeek()).fixed.find((f) => f.title === "Coffee with Priya") as Item
    const { user } = await openCard(ofEvent(event))
    expect(inCard().getAllByText("Friday").length).toBeGreaterThan(0) // the calendar: Friday's own
    await user.click(inCard().getByRole("button", { name: "Repeats" }))
    const weekly = screen.getAllByRole("option").find((o) => /^Every week|weekly/i.test(o.textContent ?? "")) ?? screen.getAllByRole("option")[1]
    await user.click(weekly)
    expect((await waitForSent("repeat")).body).toMatchObject({ id: event.id, every: expect.any(String) })
    await openCard(ofEvent(event))
    await user.click(inCard().getByRole("button", { name: /^Edit/ }))
    expect(card()).toBeNull()
    expect((await screen.findAllByDisplayValue("Coffee with Priya")).length).toBeGreaterThan(0)
  })

  it("gives shoved time back to the plan", async () => {
    const day = addDays(await today(), 5)
    const weekday = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date(`${day}T12:00:00Z`).getUTCDay()]
    const shoved = await friday.c<{ result: { created: number[] } }>("shove", { range: `21:00-22:00 ${weekday}`, decision: "shove_anyway" })
    const id = shoved.result.created[0]
    const { user } = await openCard({ key: `F${id}`, start: `${day}T21:00` })
    expect(box(`F${id}`)?.textContent).toMatch(/^Your time/)
    await user.click(await inCard().findByRole("button", { name: /Give it back/ }))
    expect((await waitForSent("unshove")).body).toEqual({ id })
  })
})

describe("the past's cards", () => {
  /** This week's plan around today, where the past is. */
  const thisWeek = async () => {
    const first = addDays(await today(), -3)
    return friday.q<Plan>("plan", { start: `${first}T00:00`, end: `${addDays(first, 7)}T00:00` })
  }
  const open = async (key: string) => {
    cleanup()
    const opened = await openFriday("/")
    await waitFor(() => expect(box(key)).not.toBeNull(), { timeout: 15_000 })
    await opened.user.click(box(key) as HTMLElement)
    await detailed()
    return opened
  }
  const long = (b: { start: string; end: string }) => Date.parse(`${b.end}:00Z`) - Date.parse(`${b.start}:00Z`) >= 30 * 60_000

  it("puts a sitting's times right, or removes it", async () => {
    const sitting = ((await thisWeek()).sessions ?? []).find(long) as Block
    const { user } = await open(sitting.key)
    expect(inCard().getByText("Timed · when you worked on it")).toBeTruthy()
    expect(inCard().queryByRole("button", { name: "Delete" })).toBeNull()
    await user.click(inCard().getByRole("button", { name: "Change when you worked" }))
    const group = inCard().getByRole("group", { name: "When you worked" })
    expect(within(group).getByLabelText("Started")).toBeTruthy()
    await user.click(within(group).getByRole("button", { name: "Cancel" }))
    await user.click(inCard().getByRole("button", { name: "Change when you worked" }))
    await user.click(inCard().getByRole("button", { name: /Save/ }))
    expect((await waitForSent("sitting_edit")).body).toMatchObject({ id: sitting.item_id, start: sitting.start, end: sitting.end, new_start: sitting.start, new_end: sitting.end })
    await waitFor(() => expect(card()).toBeNull())
    await user.click(box(sitting.key) as HTMLElement)
    await user.click(await inCard().findByRole("button", { name: "Remove this sitting" }))
    expect((await waitForSent("sitting_delete")).body).toEqual({ id: sitting.item_id, start: sitting.start, end: sitting.end })
  })

  it("plans work counted done again if you didn't do it, and opens a finished to-do again", async () => {
    const plan = await thisWeek()
    const items = await friday.q<Item[]>("items", { status: "all" })
    const counted = plan.blocks.find((b) => b.state === "done" && long(b) && items.find((i) => i.id === b.item_id)?.status !== "done")
    if (counted) {
      const { user } = await open(counted.key)
      expect(inCard().getByText("Past · counted as done")).toBeTruthy()
      await user.click(await inCard().findByRole("button", { name: "Didn’t do it? Plan it again" }))
      expect((await waitForSent("settle")).body).toEqual({ block_key: counted.key, status: "not_done", until: counted.end })
    }
    const finished = plan.blocks.find((b) => b.state === "done" && long(b) && b.key !== counted?.key)
    if (finished) {
      const { user } = await open(finished.key)
      const again = await inCard().findByRole("button", { name: "Open again" }).catch(() => null)
      if (again) {
        await user.click(again)
        expect((await waitForSent("reopen")).body).toEqual({ id: finished.item_id })
      }
    }
    expect(counted ?? finished).toBeTruthy()
  })

  it("lets go of the card on another page, and on a press elsewhere", async () => {
    const block = (await thisWeek()).blocks.find((b) => b.key.startsWith("T") && b.state !== "gone" && b.state !== "timed") as Block
    const { user } = await open(block.key)
    fireEvent.pointerDown(document.querySelector('[data-tour="calendar"]') as HTMLElement)
    await waitFor(() => expect(card()).toBeNull())
    await user.click(box(block.key) as HTMLElement)
    await waitFor(() => expect(card()).not.toBeNull())
    await user.click(screen.getByRole("link", { name: /^To-do/ }))
    await waitFor(() => expect(card()).toBeNull())
  })
})
