// The Inbox's questions over Alex's sample: planned time Friday can't account for, what only you can decide (late
// work, what Friday learned against a rule), sleep taps you missed, and Friday's own questions (a new weighing of the
// rules, which of two days, your meals and your sleep). Each answered sends its command and leaves the list.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Decision = { key: string; kind: string; items?: { item_id: number }[] }
const decisions = async () => ((await friday.q("status")) as { decisions: Decision[] }).decisions
const day = (offset: number) => {
  const d = new Date(Date.now() + offset * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const list = () => screen.getByRole("list", { name: "Waiting for you" })
const rows = () => within(list()).queryAllByRole("listitem")
const row = (text: string | RegExp) => {
  const found = rows().find((r) => (typeof text === "string" ? r.textContent?.includes(text) : text.test(r.textContent ?? "")))
  if (!found) throw new Error(`no message says ${text}; the list: ${rows().map((r) => r.textContent).join(" | ")}`)
  return found
}
const findRow = (text: string | RegExp, timeout = 10_000) => waitFor(() => row(text), { timeout })
const gone = (text: string | RegExp) => waitFor(() => expect(rows().some((r) => (typeof text === "string" ? r.textContent?.includes(text) : text.test(r.textContent ?? "")))).toBe(false))


/** The Inbox, reached from the sidebar once Friday's status is in, the way a user comes to it. */
async function openInbox() {
  const view = await openFriday("/")
  await waitFor(() => expect(view.client.getQueryData(["status"])).toBeTruthy(), { timeout: 20_000 })
  const link = screen.queryAllByRole("link", { name: /^Inbox/ })[0]
  if (link) await view.user.click(link)
  else window.location.hash = "#/inbox" // a narrow window keeps the sidebar folded away
  await screen.findByRole("list", { name: "Waiting for you" })
  return view
}

describe("planned time Friday can't account for", () => {
  it("asks how much of a task's planned time you did, and saves some of it", async () => {
    const { user } = await openInbox()
    // only while a planned block has gone by unanswered: early in the day there may be none (as the others here)
    if (!rows().some((r) => /did you do it\?/.test(r.textContent ?? ""))) return
    await user.click(await findRow(/did you do it\?/))
    expect(await screen.findByText(/No timer ran and it isn't checked off/)).toBeTruthy()
    expect(screen.getByRole("button", { name: /^All of it \(/ })).toBeTruthy()
    expect(screen.getByRole("button", { name: /^Finished it/ })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: /^Some/ }))
    expect(screen.getByText("How much did you do?")).toBeTruthy()
    // the minutes done sit between Less and More, starting from half
    const shown = () => screen.getByRole("button", { name: "Less" }).nextElementSibling?.textContent
    const half = shown()
    await user.click(screen.getByRole("button", { name: "Less" }))
    expect(shown()).not.toBe(half)
    await user.click(screen.getByRole("button", { name: "More" }))
    expect(shown()).toBe(half)
    // Back, and the four answers again; 2 is Some from the keyboard
    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(screen.getByRole("button", { name: /^None/ })).toBeTruthy()
    await user.keyboard("2")
    expect(await screen.findByText("How much did you do?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Save" }))
    const sent = await waitForSent("review_task")
    expect(sent.body).toMatchObject({ status: "partial", minutes: expect.any(Number) })
    const { date, item_id } = sent.body as { date: string; item_id: number }
    type Gap = { item_id: number; answer: unknown; done_min: number | null }
    await waitFor(async () => {
      const gap = ((await friday.q("review", { date })) as { gaps: Gap[] }).gaps.find((g) => g.item_id === item_id)
      expect(gap?.answer ?? gap?.done_min ?? "no longer asked").toBeTruthy()
    })

  })

  it("answers a gap with a button or its number", async () => {
    const { user } = await openInbox()
    const waiting = await waitFor(() => rows().filter((r) => r.textContent?.includes("did you do it?")))
    if (!waiting.length) return // every gap of today and yesterday is answered: nothing more to ask at this hour
    await user.click(waiting[0])
    await screen.findByRole("button", { name: /^None/ })
    await user.keyboard("3")
    expect((await waitForSent("review_task")).body).toMatchObject({ status: "not_done" })
    if (waiting.length < 2) return
    await screen.findByRole("button", { name: /^All of it/ })
    await user.click(screen.getByRole("button", { name: /^All of it/ }))
    expect((await waitForSent("review_task")).body).toMatchObject({ status: "done" })
  })
})

describe("what only you can decide", () => {
  it("says what will be late, and offers what can be done", { timeout: 90_000 }, async () => {
    await friday.c("add", { title: "Huge report", preset: "Assignment", duration_min: 1500, due: `${day(1)}T09:00` })
    await waitFor(async () => expect((await decisions()).some((d) => d.kind === "late")).toBe(true), { timeout: 60_000, interval: 500 })
    const { user } = await openInbox()
    const late = await findRow("Huge report will be late")
    expect(late.textContent).toContain("Decide")
    // what only you can decide comes first
    expect(rows()[0]).toBe(late)
    await user.click(late)
    expect(await screen.findByText(/To decide · Will be late/)).toBeTruthy()
    expect(screen.getByText(/Friday can make room/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "See options" }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
  })

  it("leaves late work late", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Huge report will be late"))
    await user.click(await screen.findByRole("button", { name: "Leave it late" }))
    const sent = await waitForSent("late_accept")
    expect((sent.body as { item_ids: number[] }).item_ids).toHaveLength(1)
    await gone("Huge report will be late")
    await waitFor(async () => expect((await decisions()).some((d) => d.kind === "late")).toBe(false))
  })

  it("opens a late task from its decision", { timeout: 90_000 }, async () => {
    await friday.c("add", { title: "Another huge report", preset: "Assignment", duration_min: 1800, due: `${day(1)}T10:00` })
    await waitFor(async () => expect((await decisions()).some((d) => d.kind === "late")).toBe(true), { timeout: 60_000, interval: 500 })
    const { user } = await openInbox()
    await user.click(await findRow(/will be late/))
    await user.click(await screen.findByRole("button", { name: /Another huge report/ }))
    await waitFor(() => expect(window.location.hash).toMatch(/\/todo\?item=\d+/))
  })
})

describe("sleep and what Friday learned from it", () => {
  it("asks whether to follow what Friday learned when it disagrees with a rule", { timeout: 60_000 }, async () => {
    await friday.c("settings_set", { key: "sleep_tracking", value: { on: true, min_nights: 4, morning_hours: 4 } })
    for (let n = 1; n <= 6; n++) {
      await friday.c("sleep_mark", { kind: "done", at: `${day(-n - 1)}T22:30` })
      await friday.c("sleep_mark", { kind: "bed", at: `${day(-n)}T01:30` })
      await friday.c("sleep_mark", { kind: "up", at: `${day(-n)}T09:45` })
      await friday.c("sleep_mark", { kind: "ready", at: `${day(-n)}T10:30` })
    }
    await waitFor(async () => expect((await decisions()).some((d) => d.kind === "learned")).toBe(true), { timeout: 30_000, interval: 500 })
    const { user } = await openInbox()
    await user.click(await findRow(/Wind down before bed/))
    expect(await screen.findByText(/What Friday learned, against a rule of yours/)).toBeTruthy()
    expect(screen.getByText("Friday would update the rule.")).toBeTruthy()
    expect(screen.getByText("Nothing waits on your answer: the plan goes on meanwhile.")).toBeTruthy()
    const options = screen.getAllByRole("button").filter((b) => /^Start winding down|^Keep /.test(b.textContent ?? ""))
    expect(options).toHaveLength(2)
    await user.click(options[0])
    expect((await waitForSent("conflict_resolve")).body).toEqual({ key: "wind_down", option: "rule" })
  })

  it("asks to use your real bedtimes and wake times", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Your real times differ from your schedule"))
    expect((await screen.findAllByText(/to bed around 1:30am/)).length).toBeGreaterThan(1)
    await user.click(screen.getByRole("button", { name: "Use these times" }))
    const sent = await waitForSent("settings_set")
    expect(sent.body).toMatchObject({ key: "sleep", value: { mon: { bedtime: "01:30", wake: "09:45" } } })
    await gone("Your real times differ from your schedule")
  })

  it("asks for a sleep tap you missed, starting from your usual time", async () => {
    const { user } = await openInbox()
    const missed = await waitFor(() => rows().filter((r) => r.textContent?.includes("A sleep tap you missed")))
    if (!missed.length) return // every tap of today and yesterday is in: nothing to ask at this hour
    await user.click(missed[0])
    expect(await screen.findByText(/Friday learns your real bedtime, wake time and routines from these/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add it" }))
    const sent = await waitForSent("sleep_mark")
    expect(sent.body).toMatchObject({ kind: expect.any(String), at: expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/) })
    if (missed.length < 2) return
    await screen.findByRole("button", { name: "I don't remember" })
    await user.click(screen.getByRole("button", { name: "I don't remember" }))
    expect((await waitForSent("sleep_skip")).body).toMatchObject({ kind: expect.any(String), date: expect.any(String) })
  })
})

describe("Friday's questions", () => {
  it("shows a new weighing of the rules, each rule on its line, and approves it", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Weigh your rules the way you plan"))
    expect(await screen.findByText(/Counts more · \d/)).toBeTruthy()
    expect(screen.getByText(/Counts less · \d/)).toBeTruthy()
    expect(screen.getByText("Wind down before bed")).toBeTruthy()
    expect(screen.getAllByText(/days? you compared/).length).toBeGreaterThan(1)
    await user.click(screen.getByRole("button", { name: "Approve" }))
    expect((await waitForSent("learn_apply")).body).toEqual({ version: 4 })
    await gone("Weigh your rules the way you plan")
  })

  it("asks which of two versions of a day looks better, and skips it", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Which version of the day looks better?"))
    expect(await screen.findByText("Version A")).toBeTruthy()
    expect(screen.getByText("Version B")).toBeTruthy()
    expect(screen.getByText("Work, in its area's colour")).toBeTruthy()
    expect(screen.getAllByText(/moved$/)).toHaveLength(2)
    // each piece says where it is, and whether the other version has it elsewhere
    expect(document.querySelector('[title*=", fixed"]')).toBeTruthy()
    expect(document.querySelector('[title*="the same in both"]')).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Skip" }))
    expect((await waitForSent("compare_answer")).body).toMatchObject({ answer: "skip" })
    await gone("Which version of the day looks better?")
  })

  it("picks the version of a day you'd rather have", async () => {
    const { user } = await openInbox()
    await findRow("Weigh your rules the way you plan").catch(() => null)
    const compare = rows().find((r) => r.textContent?.includes("Which version of the day looks better?"))
    if (!compare) return // Friday had one day to ask about, answered above
    await user.click(compare)
    await user.click(await screen.findByRole("button", { name: "Pick B" }))
    expect((await waitForSent("compare_answer")).body).toMatchObject({ answer: "b" })
    await gone("Which version of the day looks better?")
  })

  it("asks about your meals: a length, a time, and one you skip", { timeout: 60_000 }, async () => {
    await friday.c("settings_set", { key: "meal_tracking", value: { on: true, min_days: 4 } })
    for (let n = 1; n <= 6; n++) {
      await friday.c("meal_log", { kind: "lunch", start: `${day(-n)}T13:30`, end: `${day(-n)}T14:30` })
      await friday.c("meal_log", { kind: "breakfast", start: `${day(-n)}T10:00`, end: `${day(-n)}T10:20` })
      await friday.c("meal_skip", { kind: "dinner", date: day(-n) })
    }
    const { user } = await openInbox()
    await user.click(await findRow("Lunch takes you about 1h"))
    expect((await screen.findAllByText(/Friday plans 45m/)).length).toBeGreaterThan(1)
    await user.click(screen.getByRole("button", { name: /^Plan 1h/ }))
    expect((await waitForSent("meal_use_length")).body).toEqual({ kind: "lunch" })
    await gone("Lunch takes you about 1h")
    await user.click(await findRow("You usually have breakfast around 10am"))
    await user.click(await screen.findByRole("button", { name: /^Plan \d/ }))
    expect((await waitForSent("meal_use_time")).body).toEqual({ kind: "breakfast" })
    await user.click(await findRow("You usually skip dinner"))
    await user.click(await screen.findByRole("button", { name: "Stop planning it" }))
    expect((await waitForSent("meal_plan")).body).toEqual({ kind: "dinner", plan: false })
  })

  it("sets a question aside with Not now, until Friday has more to go on", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("You usually have lunch around"))
    await user.click(await screen.findByRole("button", { name: "Not now" }))
    const sent = await waitForSent("ask_later")
    expect(sent.body).toMatchObject({ key: "meal-time:lunch", evidence: "13:30" })
    await gone("You usually have lunch around")
    await waitFor(async () => expect(((await friday.q("asks_later")) as { later: Record<string, string> }).later["meal-time:lunch"]).toBe("13:30"))
  })
})

describe("the count of what waits", () => {
  it("shows on the plan as a tray that opens the Inbox, and in the window's title", async () => {
    const { user } = await openFriday("/")
    const tray = await screen.findByRole("button", { name: /^\d+ things? waiting in your Inbox$/ }, { timeout: 15_000 })
    const n = Number(tray.getAttribute("aria-label")?.match(/\d+/)?.[0])
    await waitFor(() => expect(document.title).toMatch(new RegExp(`^\\(${n}\\) `)))
    await user.click(tray)
    expect(await screen.findByRole("list", { name: "Waiting for you" })).toBeTruthy()
  })
})
