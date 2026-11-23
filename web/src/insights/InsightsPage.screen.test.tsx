// Insights over Alex's sample: the last weeks in numbers, how long things take by kind and the switch to adjust
// estimates, when work gets done, what Friday learned so far, the load ahead; the week's look back with its choices;
// and the Sleep and Meals tabs, once tracking is on and there are nights and meals to learn from.
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"
import { addDays } from "@/lib/time"

const day = (offset: number) => {
  const d = new Date(Date.now() + offset * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
const tabs = () => screen.getByRole("group", { name: "Insights" })

describe("Insights → Trends", () => {
  it("opens on the last four weeks in three numbers", async () => {
    await openFriday("/insights?tab=trends")
    expect(await screen.findByText("things finished in 4 weeks")).toBeTruthy()
    expect(screen.getByText("of work recorded")).toBeTruthy()
    expect(screen.getByText("how long things take against the estimate")).toBeTruthy()
    expect(screen.getByText(/^Based on \d+ finished things?$/)).toBeTruthy()
    expect(within(tabs()).getByRole("button", { name: /Trends/ }).getAttribute("aria-pressed")).toBe("true")
  })

  it("looks back over two or twelve weeks instead", async () => {
    const { user } = await openFriday("/insights?tab=trends")
    await screen.findByText("things finished in 4 weeks")
    await user.click(screen.getByRole("button", { name: "2 weeks" }))
    expect(await screen.findByText("things finished in 2 weeks")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "12 weeks" }))
    expect(await screen.findByText("things finished in 12 weeks")).toBeTruthy()
  })

  it("says how long each kind really takes against its estimate", async () => {
    await openFriday("/insights?tab=trends")
    expect(await screen.findByText("How long things really take")).toBeTruthy()
    expect(screen.getByText("Assignment")).toBeTruthy()
    // the sample is lived up to today, so its numbers move day to day: each kind says how it compares, and how many
    expect(screen.getAllByText(/^(\d+(\.\d+)?× as (long|quick)|On estimate) \(\d+\)$/).length).toBeGreaterThan(0)
    expect(screen.getByText("Quicker")).toBeTruthy()
    expect(screen.getByText("Longer")).toBeTruthy()
  })

  it("turns on adjusting new estimates from what it learned", async () => {
    const { user } = await openFriday("/insights?tab=trends")
    const adjust = await screen.findByRole("switch", { name: "Adjust estimates" })
    expect(adjust.getAttribute("aria-checked")).toBe("false")
    expect(await screen.findByText(/^Learned from \d+ finished things\.$/)).toBeTruthy()
    await user.click(adjust)
    expect((await waitForSent("learn_module")).body).toEqual({ module: "durations", use: true })
    await waitFor(async () => expect(((await friday.q("learning")) as { durations: { in_use: boolean } }).durations.in_use).toBe(true))
  })

  it("shows when work gets done, hour by hour, with the pattern in words", async () => {
    await openFriday("/insights?tab=trends")
    expect(await screen.findByText("When you get things done")).toBeTruthy()
    expect(screen.getByText(/You get the most done on/)).toBeTruthy()
    for (const d of ["Mon", "Sun"]) expect(screen.getAllByText(d).length).toBeGreaterThan(0)
    expect(document.querySelector('[title^="Sat 3pm"]')).toBeTruthy()
    // an hour's cell says its weeks (16 Nov: "Mon 11pm, 357 min" was three Mondays added up, read as one hour)
    expect(document.querySelector('[title^="Sat 3pm"]')?.getAttribute("title")).toMatch(/^Sat 3pm: (nothing|\d+[hm].*) in the last 4 weeks$/)
    expect(screen.getByText("Time worked in each hour, the last 4 weeks together")).toBeTruthy()
  })

  it("says what Friday learned so far, and how many questions about it wait in the Inbox", async () => {
    const { user } = await openFriday("/insights?tab=trends")
    expect(await screen.findByText("What Friday learned")).toBeTruthy()
    expect(screen.getByText("So far")).toBeTruthy()
    expect(screen.getByText("How long things take")).toBeTruthy()
    expect(await screen.findByText(/In use from \d+ finished things you timed|Learned from \d+ finished things you timed/)).toBeTruthy()
    expect(screen.getByText(/of 4 times you started one kind of work/)).toBeTruthy()
    expect(screen.getByText(/planned blocks? watched/)).toBeTruthy()
    expect(screen.getByText("Off: turn it on to learn your bedtime and wake time")).toBeTruthy()
    expect(screen.getByText("Off: turn it on to learn when you eat")).toBeTruthy()
    expect(screen.getByText(/days? you compared/)).toBeTruthy()
    expect(screen.getAllByRole("img", { name: /^\d+ of \d+$/ }).length).toBeGreaterThan(0)
    const link = await screen.findByRole("link", { name: /questions? about what Friday learned waits? in your Inbox/ })
    await user.click(link)
    expect(await screen.findByRole("list", { name: "Waiting for you" })).toBeTruthy()
  })

  it("says how often late-looking work was finished on time anyway", { timeout: 60_000 }, async () => {
    // the sample's own plans may have shown nothing late: ten hours due in three, which the plan shows late, done on time
    const soon = new Date(Date.now() + 3 * 3_600_000)
    const at = `${soon.getFullYear()}-${String(soon.getMonth() + 1).padStart(2, "0")}-${String(soon.getDate()).padStart(2, "0")}T${String(soon.getHours()).padStart(2, "0")}:00`
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Crammed lab writeup", preset: "Assignment", due: at, duration_min: 600, firmness: "hard" })
    const id = made.result.item.id
    type Status = { late_items: { item_id: number }[] }
    await waitFor(async () => expect((await friday.q<Status>("status")).late_items.map((l) => l.item_id)).toContain(id), { timeout: 30_000, interval: 500 })
    await friday.c("done", { id })
    await openFriday("/insights?tab=trends")
    expect(await screen.findByText("Late on paper, on time in practice")).toBeTruthy()
    expect(screen.getByText(/^[1-9]\d* of \d+ things your plans showed late you finished on time \(\d+%\)\.$/)).toBeTruthy()
  })

  // 15 Nov: a client's Load ahead said a week held 1 h more than they could do, and its button opened what gives when
  // work is late, which said "Everything fits. Nothing is going late."
  it("says plainly when a week holds more than your usual with nothing late, and offers to lighten it", { timeout: 120_000 }, async () => {
    const { today } = await friday.q<{ today: string }>("calendar", { start: "2026-01-01", days: "1" })
    // due Sunday, more than the rest of the week's usual room: the week holds more, and it can all be done on time
    for (const [title, hours] of [["Big reading", 16], ["Big reading 2", 8]] as const) await friday.c("add", { title, preset: "Assignment", duration_min: hours * 60, due: `${addDays(today, 3)}T23:00` })
    type Week = { hours: number; capacity: number }
    await waitFor(async () => expect((await friday.q<Week[]>("load", { weeks: "8" })).some((w) => w.hours > w.capacity + 0.5)).toBe(true), { timeout: 60_000, interval: 1000 })
    await waitFor(async () => expect((await friday.q<{ late_items: unknown[] }>("status")).late_items).toEqual([]))
    const { user } = await openFriday("/insights?tab=trends")
    expect(await screen.findByText("Load ahead")).toBeTruthy()
    expect(screen.getByText("Capacity")).toBeTruthy()
    expect(screen.getByText("Deadline")).toBeTruthy()
    expect((await screen.findAllByText(/^\d+ \/ \d+ h$/)).length).toBeGreaterThan(1)
    const over = await screen.findByText(/^Mon \d+’s week: [\d.]+ h planned, [\d.]+ h past your usual [\d.]+ h\. Nothing will be late\.$/)
    expect(screen.queryByText(/more than you can do/)).toBeNull()
    await user.click(within(over.parentElement as HTMLElement).getByRole("button", { name: "Lighten that week" }))
    const dialog = within(await screen.findByRole("dialog", { name: /^Lighten Mon \d+’s week$/ }))
    // flexible work there, started the week after, each tried on a copy of the plan: never what gives when work is late
    const options = await dialog.findAllByRole("button", { name: /^Start .+ on Mon \d+/ }, { timeout: 30_000 })
    expect(dialog.queryByText(/Everything fits|Nothing is going late/)).toBeNull()
    expect(dialog.getByText(/^Each was tried on a copy of your plan: none makes anything late/)).toBeTruthy()
    await user.click(options[0])
    expect(options[0].getAttribute("aria-pressed")).toBe("true")
    expect(dialog.getByText(/^[\d.]+ h after these, your usual [\d.]+ h$/)).toBeTruthy()
    await user.click(dialog.getByRole("button", { name: /^Apply/ }))
    const edit = (await waitForSent("edit")).body as { id: number; release: string }
    expect(edit.release).toMatch(/^\d{4}-\d{2}-\d{2}T04:00$/)
    expect(await screen.findByRole("button", { name: "Undo" })).toBeTruthy()
  })

  it("says how many things will be late when the week holds more than can be done", { timeout: 90_000 }, async () => {
    await friday.c("add", { title: "Enormous project", preset: "Assignment", duration_min: 60 * 60, due: `${day(5)}T23:00` })
    type Week = { hours: number; capacity: number }
    await waitFor(async () => expect((await friday.q<{ late_items: unknown[] }>("status")).late_items.length).toBeGreaterThan(0), { timeout: 60_000, interval: 1000 })
    await waitFor(async () => expect((await friday.q<Week[]>("load", { weeks: "8" })).some((w) => w.hours > w.capacity + 0.5)).toBe(true), { timeout: 60_000, interval: 1000 })
    const { user } = await openFriday("/insights?tab=trends")
    const over = await screen.findByText(/’s week: [\d.]+ h planned, [\d.]+ h past your usual [\d.]+ h\. (1 thing|\d+ things) will be late\.$/)
    await user.click(within(over.parentElement as HTMLElement).getByRole("button", { name: "Lighten that week" }))
    const dialog = within(await screen.findByRole("dialog"))
    // what's late has its own options, a tap away
    await user.click(await dialog.findByRole("button", { name: "See what’s late" }))
    expect(await screen.findByRole("dialog", { name: "What gives when it can't all fit" })).toBeTruthy()
  })
})

describe("Insights → This week", () => {
  it("looks back on the week: where the time went, what's finished, carried over and coming", async () => {
    const { user } = await openFriday("/insights?tab=week")
    expect(await screen.findByText(/^Week of /, {}, { timeout: 15_000 })).toBeTruthy()
    expect(screen.getByText(/You finished \d+ things? and worked [\d.]+ of [\d.]+ planned hours/)).toBeTruthy()
    expect(screen.getByText("Where the time went")).toBeTruthy()
    expect(screen.getByText("Finished")).toBeTruthy()
    expect(screen.getByText("Carried over")).toBeTruthy()
    expect(screen.getByText("Coming up")).toBeTruthy()
    expect(screen.getByText("Choices apply when you finish")).toBeTruthy()
    // a to-do in a row opens on the To-do page
    const item = screen.getAllByRole("button").find((b) => b.className.includes("fr-hover-text") && /Lunch|Dinner|gym|FWS/.test(b.textContent ?? ""))
    expect(item).toBeTruthy()
    await user.click(item as HTMLElement)
    await waitFor(() => expect(window.location.hash).toContain("/todo?item="))
  })

  // 22 Nov: "suggested" on the tab was "super vague - and i have no idea what it means or what i'm supposed to do"
  it("says what the review is for and what to do, each step going to its choice; no tab says suggested", async () => {
    const went: string[] = []
    const scroll = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function (this: Element) {
      went.push(this.id)
    }
    try {
      const { user } = await openFriday("/insights?tab=week")
      expect(await screen.findByText(/^Week of /, {}, { timeout: 15_000 })).toBeTruthy()
      expect(within(tabs()).queryByText("suggested")).toBeNull()
      const steps = screen.getByRole("list", { name: "What to do" })
      expect(screen.getByText(/^(Your week ends today: see how it went and choose what changes next week\.|See how your week is going\. On \w+, choose what changes next week\.)$/)).toBeTruthy()
      for (const [step, id] of [["Say how the week felt", "review-feel"], ["Pick next week's pace", "review-pace"]] as const) {
        await user.click(within(steps).getByRole("button", { name: step }))
        expect(went.at(-1)).toBe(id)
      }
      expect(within(steps).getByText(/Finish review and plan the week/)).toBeTruthy()
    } finally {
      Element.prototype.scrollIntoView = scroll
    }
  })

  it("saves how the week felt and a note, and suggests a pace from the feeling", async () => {
    const { user } = await openFriday("/insights?tab=week")
    await screen.findByText(/^Week of /, {}, { timeout: 15_000 })
    // 22 Nov: no "suggested" beside a pace (as on the tab, H237): the line under them says which is picked and why
    const pace = () => screen.getByText("Pace for next week").parentElement as HTMLElement
    expect(within(pace()).queryByText("suggested")).toBeNull()
    expect(within(pace()).getByText(/^\w+, your usual pace, is picked\. Pick another to change it\./)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Rough" }))
    expect((await waitForSent("week_note")).body).toMatchObject({ feel: "Rough" })
    expect(await screen.findByText("Easy is picked because the week felt rough: a lighter week to recover. Pick another to change it. Deadlines still hold.")).toBeTruthy()
    expect(screen.getByText(/pace Easy$/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Great" }))
    expect(await screen.findByText(/pace Push$/)).toBeTruthy()
    expect(within(pace()).getByText(/^Push is picked because the week felt great\./)).toBeTruthy()
    expect(within(pace()).queryByText("suggested")).toBeNull()
    const notes = screen.getByPlaceholderText(/A note for next Sunday/)
    await user.type(notes, "Start problem sets on Mondays")
    await user.click(screen.getByText("Anything to remember?"))
    expect((await waitForSent("week_note")).body).toMatchObject({ notes: "Start problem sets on Mondays" })
  })

  it("brings back the note saved for the week", async () => {
    await openFriday("/insights?tab=week")
    await screen.findByText(/^Week of /, {}, { timeout: 15_000 })
    expect((screen.getByPlaceholderText(/A note for next Sunday/) as HTMLTextAreaElement).value).toBe("Start problem sets on Mondays")
  })

  it("finishes the review: carried work moved or dropped, and the pace for next week", async () => {
    type Week = { start: string; end: string; carried: { item_id: number; title: string; when: string | null }[] }
    const week = await friday.q<Week>("week_review", { date: day(0) })
    const monday = new Date(Date.parse(`${week.end}T12:00`) + 86_400_000).toISOString().slice(0, 10)
    // work due after next Monday can wait for it; something else is dropped
    const later = week.carried.find((c) => !!c.when && c.when.slice(0, 10) > monday)
    const other = week.carried.find((c) => c !== later && !/^(Breakfast|Lunch|Dinner|gym)$/.test(c.title))
    const { user } = await openFriday("/insights?tab=week")
    await screen.findByText(/^Week of /, {}, { timeout: 15_000 })
    // carried work's row, with its choices (work due before next Monday has no Next week)
    const rowOf = (title: string, choice: string) => screen.getAllByText(title).map((t) => t.closest(".fr-row")).find((r) => r && within(r as HTMLElement).queryByRole("button", { name: choice })) as HTMLElement
    if (later) await user.click(within(rowOf(later.title, "Next week")).getByRole("button", { name: "Next week" }))
    if (other) await user.click(within(rowOf(other.title, "Drop")).getByRole("button", { name: "Drop" }))
    const changes = Number(!!later) + Number(!!other)
    expect(screen.getByText(new RegExp(`^${changes} changes to carried work`))).toBeTruthy()
    await user.click(await screen.findByRole("button", { name: /^Easy/ }))
    // a double click finishes it once (audit, 12 Nov: the second dropped and moved the same work again)
    await user.dblClick(screen.getByRole("button", { name: /Finish review and plan the week/ }))
    if (later) expect((await waitForSent("edit")).body).toEqual({ id: later.item_id, release: `${monday}T00:00` })
    if (other) expect((await waitForSent("drop")).body).toEqual({ id: other.item_id })
    expect((await waitForSent("pace", 15_000)).body).toEqual({ name: "Easy", for_days: 7 })
    expect(await screen.findByText(/The week is reviewed/, undefined, { timeout: 15_000 })).toBeTruthy()
    expect(sent.filter((s) => s.name === "pace")).toHaveLength(1)
    expect(sent.filter((s) => s.name === "drop")).toHaveLength(Number(!!other))
    if (later) {
      const moved = (await friday.q<{ id: number; release: string | null }[]>("items", { status: "all" })).find((i) => i.id === later.item_id)
      expect(moved?.release).toBe(`${monday}T00:00`)
    }
    await user.click(screen.getByRole("button", { name: "See the plan" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("offers only Keep or Drop for carried work due before next Monday", async () => {
    // "Next week" starts it next Monday, which can't be after its due: Lunch (due today) can't wait a week
    await openFriday("/insights?tab=week")
    await screen.findByText(/^Week of /, {}, { timeout: 15_000 })
    const rows = screen.getAllByText("Lunch").map((t) => t.closest(".fr-row")).filter(Boolean) as HTMLElement[]
    const lunch = rows.find((r) => within(r).queryByRole("button", { name: "Keep" })) as HTMLElement
    expect(within(lunch).getByRole("button", { name: "Drop" })).toBeTruthy()
    expect(within(lunch).queryByRole("button", { name: "Next week" })).toBeNull()
  })
})

describe("Insights → Sleep and Meals", () => {
  it("shows nothing learned while tracking is off, with the switch to turn it on", async () => {
    const { user } = await openFriday("/insights?tab=sleep")
    expect(await screen.findByRole("switch", { name: "Track my sleep" })).toBeTruthy()
    expect(screen.queryByText("usually to bed")).toBeNull()
    await user.click(within(tabs()).getByRole("button", { name: /Meals/ }))
    expect(await screen.findByRole("switch", { name: "Track my meals" })).toBeTruthy()
    expect(window.location.hash).toContain("tab=meals")
  })

  it("shows your nights: the usual times, the timeline and what differs from your schedule", async () => {
    await friday.c("settings_set", { key: "sleep_tracking", value: { on: true, min_nights: 4, morning_hours: 4 } })
    for (let n = 1; n <= 6; n++) {
      await friday.c("sleep_mark", { kind: "done", at: `${day(-n - 1)}T22:30` })
      await friday.c("sleep_mark", { kind: "bed", at: `${day(-n)}T01:30` })
      await friday.c("sleep_mark", { kind: "up", at: `${day(-n)}T09:45` })
      await friday.c("sleep_mark", { kind: "ready", at: `${day(-n)}T10:30` })
    }
    await friday.c("nap_log", { start: `${day(-2)}T15:00`, end: `${day(-2)}T15:40` })
    const { user } = await openFriday("/insights?tab=sleep")
    expect(await screen.findByText("usually to bed")).toBeTruthy()
    expect(screen.getByText("usually up")).toBeTruthy()
    expect(screen.getAllByText("1:30am").length).toBeGreaterThan(0)
    expect(screen.getAllByText("9:45am").length).toBeGreaterThan(0)
    expect(screen.getByText("from done with work to bed")).toBeTruthy()
    expect(screen.getByText("from up to ready to work")).toBeTruthy()
    expect(screen.getByText(/a nap, usually|naps? in two weeks/)).toBeTruthy()
    // the timeline: a night pointed at says its times
    expect(screen.getByText("Point at a night for its times")).toBeTruthy()
    const label = screen.getAllByText(new RegExp(`^\\w{3} ${Number(day(-2).slice(8, 10))}$`))[0]
    fireEvent.mouseEnter(label.parentElement as HTMLElement)
    expect(await screen.findByText(/bed 1:30am, up 9:45am, ready 10:30am/)).toBeTruthy()
    fireEvent.mouseLeave(label.parentElement as HTMLElement)
    expect(await screen.findByText("Point at a night for its times")).toBeTruthy()
    // what Friday learned: real times differ, asked in the Inbox, or set them yourself
    expect(screen.getAllByText("Your real times differ from your schedule").length).toBeGreaterThan(0)
    expect(screen.getByText(/Weekday mornings: up around/)).toBeTruthy()
    expect(screen.getByText(/Your weekday mornings take about 45m from up to ready/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /1 question about these times waits in your Inbox/ })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "or set them yourself" }))
    await waitFor(() => expect(window.location.hash).toContain("/settings/schedule"))
  })

  it("shows your meals: when you usually eat, the timeline and what Friday learned", async () => {
    await friday.c("settings_set", { key: "meal_tracking", value: { on: true, min_days: 4 } })
    for (let n = 1; n <= 6; n++) {
      await friday.c("meal_log", { kind: "lunch", start: `${day(-n)}T13:30`, end: `${day(-n)}T14:30` })
      await friday.c("meal_log", { kind: "breakfast", start: `${day(-n)}T10:00`, end: `${day(-n)}T10:20` })
      await friday.c("meal_skip", { kind: "dinner", date: day(-n) })
    }
    await openFriday("/insights?tab=meals")
    expect(await screen.findByText(/Lunch on weekdays, 1h/)).toBeTruthy()
    expect(screen.getByText(/Breakfast on weekdays, 20m/)).toBeTruthy()
    expect(screen.getAllByText(/at a regular time, never skipped/).length).toBeGreaterThan(0)
    expect(screen.getByText(/always skipped/)).toBeTruthy()
    expect(screen.getByText("Point at a day for its meals")).toBeTruthy()
    const label = screen.getAllByText(new RegExp(`^\\w{3} ${Number(day(-2).slice(8, 10))}$`))[0]
    fireEvent.mouseEnter(label.parentElement as HTMLElement)
    expect(await screen.findByText(/lunch 1:30pm–2:30pm/)).toBeTruthy()
    expect(screen.getByText(/dinner skipped/)).toBeTruthy()
    fireEvent.mouseLeave(label.parentElement as HTMLElement)
    expect(screen.getByText("What Friday learned from your meals")).toBeTruthy()
    expect(screen.getByText(/takes you about/)).toBeTruthy()
    expect(screen.getAllByText(/You usually have/).length).toBeGreaterThan(0)
    expect(screen.getByText(/You usually skip dinner/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /questions about your meals wait in your Inbox/ })).toBeTruthy()
  })

  it("says in Trends how far sleep and meals have got", async () => {
    await openFriday("/insights?tab=trends")
    expect(await screen.findByText(/Learned from 6 nights: suggests a new time/)).toBeTruthy()
    expect(await screen.findByText(/Breakfast about 10am, 20m/)).toBeTruthy()
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(2)
  })

  it("closes a night's card with Enter on Cancel, saving nothing", async () => {
    await friday.c("settings_set", { key: "sleep_tracking", value: { on: true, min_nights: 4, morning_hours: 4 } })
    const { user } = await openFriday("/insights?tab=sleep")
    const nights = await screen.findAllByTitle("Change this night", {}, { timeout: 10_000 })
    await user.click(nights.at(-1) as HTMLElement)
    const card = screen.getAllByRole("group").find((g) => / night$/.test(g.getAttribute("aria-label") ?? "")) as HTMLElement
    sent.length = 0
    within(card).getByRole("button", { name: "Cancel" }).focus()
    await user.keyboard("{Enter}")
    await waitFor(() => expect(screen.getAllByRole("group").some((g) => / night$/.test(g.getAttribute("aria-label") ?? ""))).toBe(false))
    expect(sent.map((s) => s.name)).toEqual([])
  })
})
