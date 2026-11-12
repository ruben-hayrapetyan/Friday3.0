// The Inbox over Alex's sample: what came in from mail and calendars (a suggestion each), what Friday set aside as
// something you have already, going over everything again, and copies of a task. Each message opens beside the list;
// dealing with one sends its command, and the list moves on.
import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Suggestion = { id: number; command: string; input: Record<string, unknown> }
type Inbox = { suggestions: Suggestion[]; set_aside: { id: number; title: string }[] }

const list = () => screen.getByRole("list", { name: "Waiting for you" })
/** The message in the list whose row says `text`. */
const row = (text: string | RegExp) => {
  const found = within(list())
    .getAllByRole("listitem")
    .find((r) => (typeof text === "string" ? r.textContent?.includes(text) : text.test(r.textContent ?? "")))
  if (!found) throw new Error(`no message says ${text}; the list: ${within(list()).getAllByRole("listitem").map((r) => r.textContent).join(" | ")}`)
  return found
}
const findRow = (text: string | RegExp) => waitFor(() => row(text), { timeout: 10_000 })
const current = () => within(list()).getAllByRole("listitem").find((r) => r.getAttribute("aria-current") === "true")


/** The Inbox, reached from the sidebar once Friday's status is in, the way a user comes to it (opening it straight
 * away, before status loads, is its own test below: it once rendered without end). */
async function openInbox() {
  const view = await openFriday("/")
  await waitFor(() => expect(view.client.getQueryData(["status"])).toBeTruthy(), { timeout: 20_000 })
  const link = screen.queryAllByRole("link", { name: /^Inbox/ })[0]
  if (link) await view.user.click(link)
  else window.location.hash = "#/inbox" // a narrow window keeps the sidebar folded away
  await screen.findByRole("list", { name: "Waiting for you" })
  return view
}

describe("the Inbox", () => {
  it("opens straight at /inbox before Friday's status has loaded", async () => {
    await openFriday("/inbox")
    expect(await screen.findByRole("list", { name: "Waiting for you" })).toBeTruthy()
  })

  it("lists everything waiting, counts it, and opens the most pressing first", async () => {
    await openInbox()
    await findRow("PHYS 1112 practice prelim")
    await findRow("Weigh your rules the way you plan")
    expect(screen.getByText(/^\d+ to deal with$/)).toBeTruthy()
    // the sample's mail and calendar each sent one
    expect(row("PHYS 1112 practice prelim").textContent).toContain("Gmail")
    expect(row("Advising appointment").textContent).toContain("A change")
    // something is open beside the list, and it is the row marked current
    expect(current()).toBeTruthy()
  })

  it("moves between messages with j and k, and the arrow keys", async () => {
    const { user, client } = await openInbox()
    await findRow("Which version of the day looks better?")
    await findRow("PHYS 1112 practice prelim")
    // everything the list is made from is in, so it holds still while we move through it
    await waitFor(() => expect(client.isFetching()).toBe(0), { timeout: 15_000 })
    /** The message `by` rows from the one open now: the same message even if the list fills in meanwhile. */
    const step = (by: number) => {
      const all = within(list()).getAllByRole("listitem")
      return all[Math.max(0, Math.min(all.length - 1, all.indexOf(current() as HTMLElement) + by))]
    }
    const top = within(list()).getAllByRole("listitem")[0]
    expect(current()).toBe(top)
    for (const [key, by] of [["j", 1], ["{ArrowDown}", 1], ["k", -1], ["{ArrowUp}", -1]] as const) {
      const next = step(by)
      const all = within(list()).getAllByRole("listitem")
      const from = all.indexOf(current() as HTMLElement)
      await user.keyboard(key)
      await waitFor(() => expect(current(), `${key} from ${from} of ${all.length}: now ${within(list()).getAllByRole("listitem").indexOf(current() as HTMLElement)} of ${within(list()).getAllByRole("listitem").length}, focus ${document.activeElement?.tagName}`).toBe(next))
    }
  })

  it("shows a suggestion with the words it came from and the source they're in", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("PHYS 1112 practice prelim"))
    expect(await screen.findByText(/Found in Practice prelim posted, Gmail/)).toBeTruthy()
    expect(screen.getByText(/90% sure/)).toBeTruthy()
    // the due date's own words, quoted under it, and highlighted in the mail it came from
    expect(screen.getAllByText("Monday, Nov 16").length).toBeGreaterThan(0)
    expect(screen.getByText("From the source")).toBeTruthy()
    expect(screen.getByText(/Do the practice prelim before the review session/)).toBeTruthy()
    // work's length always shows, Friday's guess said as one
    expect(screen.getByText(/Friday’s guess/)).toBeTruthy()
    expect(screen.getByRole("button", { name: /Accept/ })).toBeTruthy()
    expect(screen.getByText(/Accepting adds it and Friday plans it/)).toBeTruthy()
  })

  it("edits a suggestion's fields, then accepts it with the edits", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("PHYS 1112 practice prelim"))
    await user.click(await screen.findByRole("button", { name: /^Edit/ }))
    const title = screen.getByRole("textbox", { name: "Title" })
    await user.clear(title)
    await user.type(title, "Practice prelim 2")
    // the kind as a chip, and a length typed in words
    const chips = screen.getAllByRole("button", { pressed: false }).filter((b) => b.className.includes("fr-chip"))
    expect(chips.length).toBeGreaterThan(0)
    await user.click(screen.getByRole("button", { name: "Exam prep" }))
    const length = screen.getByRole("textbox", { name: "Length" })
    await user.clear(length)
    await user.type(length, "3h{Enter}")
    expect(screen.getAllByText("edited").length).toBeGreaterThanOrEqual(2)
    await user.click(screen.getByRole("button", { name: /Done editing/ }))
    expect(screen.getAllByText("Practice prelim 2").length).toBeGreaterThan(0)
    await user.click(screen.getByRole("button", { name: /^Accept/ }))
    const sent = await waitForSent("suggestion_accept")
    expect(sent.body).toMatchObject({ id: 151, edits: { title: "Practice prelim 2", preset: "Exam prep", duration_min: 180 } })
    // it stays in the list, greyed and said Accepted, and the next message opens
    await waitFor(() => expect(row("PHYS 1112 practice prelim").textContent).toContain("Accepted"))
    expect(current()).not.toBe(row("PHYS 1112 practice prelim"))
    const inbox = await friday.q<Inbox>("inbox")
    expect(inbox.suggestions.map((s) => s.id)).not.toContain(151)
    const items = await friday.q<{ title: string; duration_min: number | null }[]>("items")
    expect(items.find((i) => i.title === "Practice prelim 2")?.duration_min).toBe(180)
    // opened again: what happened, and Undo to answer it again
    await user.click(row("PHYS 1112 practice prelim"))
    const said = await screen.findByText("Accepted. It's in your plan.")
    await user.click(within(said.parentElement as HTMLElement).getByRole("button", { name: "Undo" }))
    await waitForSent("undo")
    expect(await screen.findByRole("button", { name: /^Accept/ })).toBeTruthy()
    await waitFor(async () => expect((await friday.q<Inbox>("inbox")).suggestions.some((s) => s.id === 151)).toBe(true))
    expect((await friday.q<{ title: string }[]>("items")).some((i) => i.title === "Practice prelim 2")).toBe(false)
  })

  it("weighs what accepting a changed event would do, and rejecting it asks why", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Advising appointment"))
    // a change to an event Friday has: Update it, with what it would do either way
    expect(await screen.findByRole("button", { name: /Update it/ })).toBeTruthy()
    expect(screen.getByText("If you accept")).toBeTruthy()
    expect(screen.getByText("If you decline")).toBeTruthy()
    await waitFor(() => expect(screen.queryByText("Working out what it changes…")).toBeNull(), { timeout: 15_000 })
    await user.click(screen.getByRole("button", { name: /Reject/ }))
    expect((await waitForSent("suggestion_reject")).body).toEqual({ id: 150 })
    await waitFor(() => expect(row("Advising appointment").textContent).toContain("Rejected"))
    // opened again: what happened, a way back, and a line to say why
    await user.click(row("Advising appointment"))
    expect(await screen.findByText(/Rejected. It won't come back unless the source changes./)).toBeTruthy()
    const why = screen.getByPlaceholderText(/needs no time from me/)
    const remember = screen.getByRole("button", { name: "Remember" })
    expect((remember as HTMLButtonElement).disabled).toBe(true)
    await user.type(why, "Advising is on my phone already{Enter}")
    const saved = await waitForSent("settings_set")
    expect(saved.body).toMatchObject({ key: "notes" })
    expect((saved.body as { value: string[] }).value).toContain("Advising is on my phone already")
    expect(await screen.findByText(/Friday will remember that/)).toBeTruthy()
  })

  it("answers a suggestion from the keyboard: e edits, r rejects", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("PHYS 1112 practice prelim"))
    await screen.findByRole("button", { name: /^Accept/ })
    await user.keyboard("e")
    expect(await screen.findByRole("textbox", { name: "Title" })).toBeTruthy()
    // typing in a field is typing, not answering
    await user.type(screen.getByRole("textbox", { name: "Title" }), "r")
    expect(screen.getByRole("button", { name: /Done editing/ })).toBeTruthy()
    await user.click(document.body)
    ;(document.activeElement as HTMLElement | null)?.blur()
    await user.keyboard("e")
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull())
    await user.keyboard("r")
    expect((await waitForSent("suggestion_reject")).body).toEqual({ id: 151 })
  })

  it("keeps what you have already aside, and asks about it after all on Add anyway", async () => {
    const { user } = await openInbox()
    const aside = await screen.findByRole("button", { name: /Set aside: 1 you have already/ })
    expect(aside.getAttribute("aria-expanded")).toBe("false")
    await user.click(aside)
    expect(screen.getByText("You have PHYS 1112 Mastering Physics 9")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add anyway" }))
    expect((await waitForSent("suggestion_restore")).body).toEqual({ id: 138 })
    await waitFor(async () => expect((await friday.q<Inbox>("inbox")).suggestions.some((s) => s.id === 138)).toBe(true))
  })

  it("accepts a suggestion with a", async () => {
    const { user } = await openInbox()
    // the suggestion, not the planned time of the task it's a copy of
    await user.click(await findRow(/^PHYS 1112 Mastering Physics 9(?!.*did you do it)/))
    await screen.findByRole("button", { name: /Accept|Update it/ })
    await user.keyboard("a")
    expect((await waitForSent("suggestion_accept")).body).toMatchObject({ id: 138, edits: {} })
  })
})

describe("going over what Friday brought in", () => {
  it("starts a go-over: a message for each task from your calendars and mail", async () => {
    const { user } = await openInbox()
    await user.click(await screen.findByRole("button", { name: "Go over everything again" }))
    await waitForSent("review_again")
    await findRow(/Go over/)
    // once started, the head's link is gone
    await waitFor(() => expect(screen.queryByRole("button", { name: "Go over everything again" })).toBeNull())
  })

  it("keeps one, changes another's kind, and takes one off the list", async () => {
    const { user } = await openInbox()
    const first = await findRow(/Go over/)
    const title = first.querySelector("span span")?.textContent ?? ""
    await user.click(first)
    expect(await screen.findByText(/Going over what Friday brought in/)).toBeTruthy()
    expect(screen.getByText(/Taking it off never touches your calendar/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Keep it" }))
    const kept = await waitForSent("reviewed")
    expect(kept.body).toMatchObject({ keep: true })
    await waitFor(() => expect(within(list()).queryAllByRole("listitem").some((r) => r.textContent?.startsWith(title) && r.textContent.includes("Go over"))).toBe(false))
    // the next go-over opened by itself: change its kind from the menu
    const kind = await screen.findByRole("button", { name: /^Kind of / })
    await user.click(kind)
    await user.click(within(screen.getByRole("listbox")).getByRole("option", { name: "Errand" }))
    const edited = await waitForSent("edit")
    expect(edited.body).toMatchObject({ preset: "Errand" })
    await user.click(screen.getByRole("button", { name: "Take it off my list" }))
    const off = await waitForSent("reviewed")
    expect(off.body).toMatchObject({ keep: false })
    expect((off.body as { ids: number[] }).ids).toHaveLength(1)
  })

  it("keeps all that are left in one go", async () => {
    const { user } = await openInbox()
    await user.click(await findRow(/Go over/))
    const all = await screen.findByRole("button", { name: /^Keep all \d+$/ })
    const n = Number(all.textContent?.match(/\d+/)?.[0])
    await user.click(all)
    const sent = await waitForSent("reviewed")
    expect((sent.body as { ids: number[] }).ids).toHaveLength(n)
    await waitFor(() => expect(within(list()).queryAllByRole("listitem").some((r) => r.textContent?.includes("Go over"))).toBe(false))
    await waitFor(async () => expect((await friday.q<{ items: unknown[] }>("to_review")).items).toHaveLength(0))
  })
})

describe("copies of a task", () => {
  it("keeps the copy you choose", async () => {
    for (const title of ["Return library books", "Return library books", "Call the bank", "Call the bank", "Buy stamps", "Buy stamps"])
      await friday.c("add", { title, preset: "Errand", duration_min: 30 })
    const { user } = await openInbox()
    await user.click(await findRow("Return library books"))
    expect(await screen.findByText(/Copies · on your list 2 times/)).toBeTruthy()
    const radios = screen.getAllByRole("radio", { name: /Keep Return library books/ })
    expect(radios).toHaveLength(2)
    const unchosen = radios.find((r) => !(r as HTMLInputElement).checked) as HTMLInputElement
    await user.click(unchosen)
    expect(unchosen.checked).toBe(true)
    await user.click(screen.getByRole("button", { name: "Keep the chosen one" }))
    const sent = await waitForSent("duplicates_merge")
    const groups = (sent.body as { groups: { keep: number; drop: number[] }[] }).groups
    expect(groups).toHaveLength(1)
    expect(groups[0].drop).toHaveLength(1)
    expect(groups[0].keep).not.toBe(groups[0].drop[0])
  })

  it("keeps copies apart when they're different", async () => {
    const { user } = await openInbox()
    await user.click(await findRow("Call the bank"))
    await user.click(await screen.findByRole("button", { name: "They’re different" }))
    const sent = await waitForSent("not_duplicates")
    expect((sent.body as { ids: number[] }).ids).toHaveLength(2)
    await waitFor(async () => expect((await friday.q<{ groups: { key: string }[] }>("duplicates")).groups.some((g) => g.key === "call bank")).toBe(false))
  })

  it("keeps one of each when several tasks have copies", async () => {
    for (const title of ["Pick up a parcel", "Pick up a parcel"]) await friday.c("add", { title, preset: "Errand", duration_min: 30 })
    const { user } = await openInbox()
    await user.click(await findRow("Buy stamps"))
    const all = await screen.findByRole("button", { name: /Keep one of each \(2\)/ })
    await user.click(all)
    const sent = await waitForSent("duplicates_merge")
    expect((sent.body as { groups: unknown[] }).groups).toHaveLength(2)
    await waitFor(async () => expect((await friday.q<{ groups: unknown[] }>("duplicates")).groups).toHaveLength(0))
  })
})

describe("the Inbox in a narrow window", () => {
  const viewport = (width: number) => (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM.setViewport({ width, height: 900 })
  afterEach(() => viewport(1440))

  it("shows the list, then one message with a way back to all of them", async () => {
    const { user } = await openInbox()
    viewport(390)
    await waitFor(() => expect(document.querySelector("[data-tight]")).toBeTruthy())
    const first = await findRow(/./)
    // the list alone: nothing is open beside it
    expect(screen.queryByRole("button", { name: /^← All \d+$/ })).toBeNull()
    await user.click(first)
    const back = await screen.findByRole("button", { name: /^← All \d+$/ })
    expect(screen.queryByRole("list", { name: "Waiting for you" })).toBeNull()
    await user.click(back)
    expect(await screen.findByRole("list", { name: "Waiting for you" })).toBeTruthy()
  })
})
