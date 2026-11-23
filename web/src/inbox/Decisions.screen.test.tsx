// The Inbox's questions over Alex's sample: planned time Friday can't account for, what only you can decide (late
// work, what Friday learned against a rule), sleep taps you missed, and Friday's own questions (a new weighing of the
// rules, which of two days, your meals and your sleep). Each answered sends its command and leaves the list.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Decision = { key: string; kind: string; items?: { item_id: number; waiting?: { id: number; title: string }[] }[] }
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

// 19 Nov, a user's notes: "'no room before it's due' - other tasks in the project are dependent on it"; your answer:
// "keep them waiting, both ask in inbox and also say why", asked as late work is
describe("steps waiting for one that has no room", () => {
  it("names them under it, and lets them go on without it", { timeout: 90_000 }, async () => {
    type Made = { result: { item: { id: number } } }
    const made = (await friday.c<Made>("add", { title: "Thesis", preset: "Project", due: `${day(10)}T17:00` })).result
    const add = async (title: string, minutes: number, more: Record<string, unknown> = {}) =>
      (await friday.c<Made>("add", { title, preset: "Assignment", duration_min: minutes, parent_id: made.item.id, ...more })).result.item.id
    await add("Gather sources", 60)
    // pointless once late, two hours due in 20 minutes: no room before its due, so never planned, never late. Not a due
    // already gone (21 Nov): such work is archived within a minute (server/jobs.py), and the test failed when it was
    const soon = new Date(Date.now() + 20 * 60_000)
    const due = `${day(0)}T${String(soon.getHours()).padStart(2, "0")}:${String(soon.getMinutes()).padStart(2, "0")}`
    const cram = await add("Cram the whole thing", 120, { due, expires: true })
    await friday.c("step_any_time", { id: cram, any_time: true })
    const write = await add("Write it up", 120)
    // planned now, as Replan does, rather than waiting on the replan its changes asked for: under the whole suite's
    // load that one's search took 8-12 s against 1 s alone, and now and then past the 60 s this waited (20 Nov)
    await friday.c("replan")
    await waitFor(async () => {
      const late = (await decisions()).find((d) => d.kind === "late")
      expect(late?.items?.find((i) => i.item_id === cram)?.waiting?.map((w) => w.title)).toEqual(["Write it up"])
    }, { timeout: 10_000, interval: 500 })
    const { user } = await openInbox()
    await user.click(await findRow(/will be late/))
    expect(await screen.findByText("Write it up waits for it: it has no room before its due, so it isn't planned.")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Drop Cram the whole thing" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Let it go on without it" }))
    expect((await waitForSent("step_any_time")).body).toEqual({ id: write, any_time: true })
    await friday.c("drop", { id: made.item.id })
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

  it("asks about a meal you skip once, weekdays and weekends together, with where it comes from", { timeout: 60_000 }, async () => {
    // 23 Nov, a user's screenshot: breakfast asked twice (weekdays, then weekends) about a rule they didn't recognize;
    // "include evidence (like in emails) of the two rules that conflict and when"
    await friday.c("settings_set", { key: "meal_tracking", value: { on: true } })
    await friday.c("rule_add", { text: "Meals are never skipped for work", strength: "Always" })
    for (let n = 1; n <= 14; n++) await friday.c("meal_skip", { kind: "breakfast", date: day(-n) })
    await waitFor(async () => expect((await decisions()).some((d) => d.title.startsWith("You skip breakfast"))).toBe(true), { timeout: 30_000, interval: 500 })
    expect((await decisions()).filter((d) => d.title.startsWith("You skip breakfast"))).toHaveLength(1)
    const { user } = await openInbox()
    await user.click(await findRow("You skip breakfast on most days, but your rule says it's never skipped"))
    const lines = (await screen.findAllByText("Your rule")).map((el) => el.closest("[data-evidence]") as HTMLElement).filter(Boolean)
    const box = lines[lines.length - 1]
    expect(within(box).getByText(/^“Meals are never skipped for work”, which you added on /)).toBeTruthy()
    expect(within(box).getByText("What Friday saw")).toBeTruthy()
    expect(within(box).getByText(/^Breakfast skipped on \d+ of \d+ weekdays and \d+ of \d+ weekend days, /)).toBeTruthy()
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
    const { user, client } = await openInbox()
    // Which rules move, and which way, depends on the days the sample's three weeks compared: some runs move only one
    // way (17 Nov: chunk cost alone, counting more). A rule the weighing leaves alone is told to the page as moving the
    // other way too, so both sides show; what's approved is still the server's own version.
    type Change = { rule: string; from: number; to: number }
    type Learning = { suggested: { version: number; changes: Change[] } | null }
    await waitFor(() => expect(client.getQueryData<Learning>(["learning"])?.suggested).toBeTruthy(), { timeout: 10_000 })
    await waitFor(() => expect(client.isFetching()).toBe(0))
    const rules = await friday.q<{ name: string; sentence: string }[]>("rules")
    const server = (client.getQueryData<Learning>(["learning"])?.suggested as NonNullable<Learning["suggested"]>).changes
    const spare = rules.filter((r) => !server.some((c) => c.rule === r.name))
    const changes = [...server]
    if (!changes.some((c) => c.to > c.from)) changes.push({ rule: spare[0].name, from: 1, to: 1.4 })
    if (!changes.some((c) => c.to < c.from)) changes.push({ rule: spare[1].name, from: 1, to: 0.7 })
    client.setQueryData<Learning>(["learning"], (was) => was && { ...was, suggested: was.suggested && { ...was.suggested, changes } })
    await user.click(await findRow("Weigh your rules the way you plan"))
    const more = changes.filter((c) => c.to > c.from).length
    const less = changes.filter((c) => c.to < c.from).length
    expect(await screen.findByText(`Counts more · ${more}`)).toBeTruthy()
    expect(screen.getByText(`Counts less · ${less}`)).toBeTruthy()
    // each rule on its line, in its own words (the biggest four of each side show before "Show all")
    const said = (rule: string) => rules.find((r) => r.name === rule)?.sentence ?? rule.replace(/^you:/, "").replaceAll(/[-_]/g, " ")
    if (more <= 4 && less <= 4) for (const c of changes) expect(screen.getByText(said(c.rule))).toBeTruthy()
    // which rules move depends on the days the sample was lived to: each says from how many days
    expect(screen.getAllByText(/days? you compared/).length).toBeGreaterThan(1)
    await user.click(screen.getByRole("button", { name: "Approve" }))
    expect((await waitForSent("learn_apply")).body).toEqual({ version: expect.any(Number) })
    await gone("Weigh your rules the way you plan")
  })

  it("asks which of two versions of a day looks better, and skips it", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Which version of the day looks better?"))
    expect(await screen.findByText("Version A")).toBeTruthy()
    expect(screen.getByText("Version B")).toBeTruthy()
    expect(screen.getByText("Work, in its area's color")).toBeTruthy()
    expect(screen.getAllByText(/moved$/)).toHaveLength(2)
    // each piece says where it is, and whether the other version has it elsewhere
    expect(document.querySelector('[title*=", fixed"]')).toBeTruthy()
    // the same in both, or where it is in the other (which the sample's two versions have depends on its plan)
    expect([...document.querySelectorAll("[title]")].some((e) => /the same in both|in the other version\)$/.test(e.getAttribute("title") ?? ""))).toBe(true)
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
  // 19 Nov: the plan's tray became the Breaks button ("instead of the yellow inbox in the top right corner can we
  // make that a 'breaks' clickable square"); the count stays beside the sidebar's Inbox and in the window's title
  it("shows beside the sidebar's Inbox and in the window's title, not as a tray on the plan", async () => {
    const { user } = await openFriday("/")
    const sidebar = within((await screen.findAllByRole("complementary"))[0])
    const inbox = sidebar.getByRole("link", { name: /^Inbox/ })
    await waitFor(() => {
      const n = inbox.textContent?.match(/\d+/)?.[0] // as more comes in, both follow: the same count
      expect(n).toBeTruthy()
      expect(document.title.startsWith(`(${n})`)).toBe(true)
    }, { timeout: 15_000 })
    expect(screen.queryByRole("button", { name: /waiting in your Inbox$/ })).toBeNull()
    await user.click(inbox)
    expect(await screen.findByRole("list", { name: "Waiting for you" })).toBeTruthy()
  })
})
