// A calendar you hide stays out of the Inbox (14 Nov: a client hid calendars in Setup's walk, and their invitations
// still came into the Inbox). Over Alex's sample: the calendar that sent "Advising appointment" (a change to one of
// its events) is hidden in Settings → Calendars as a user does it, and the Inbox no longer has the message, its count
// one less, the same in the sidebar's badge; shown again, the message is back.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Inbox = { suggestions: { id: number; source: string; source_kind: string; input: Record<string, unknown> }[] }

const list = () => screen.getByRole("list", { name: "Waiting for you" })
const titles = () => within(list()).getAllByRole("listitem").map((r) => r.textContent ?? "")
const counted = () => Number(/^(\d+) to deal with$/.exec(screen.getByText(/^\d+ to deal with$/).textContent ?? "")?.[1])
/** The sidebar's Inbox link says how many wait, as the list's heading does. */
const badge = () => Number((screen.queryAllByRole("link", { name: /^Inbox/ })[0]?.textContent ?? "").replace(/\D/g, "") || 0)

/** The Inbox, opened afresh from the sidebar once status is in: whether it has the message, and its count. */
async function inboxSays(has: boolean) {
  const view = await openFriday("/")
  await waitFor(() => expect(view.client.getQueryData(["status"])).toBeTruthy(), { timeout: 20_000 })
  await view.user.click(screen.queryAllByRole("link", { name: /^Inbox/ })[0])
  await screen.findByRole("list", { name: "Waiting for you" }, { timeout: 15_000 })
  await waitFor(() => expect(view.client.isFetching()).toBe(0), { timeout: 20_000 })
  await waitFor(() => expect(titles().some((t) => t.includes("Advising appointment"))).toBe(has), { timeout: 15_000 })
  await waitFor(() => expect(counted()).toBe(titles().length), { timeout: 15_000 })
  const n = counted()
  await waitFor(() => expect(badge()).toBe(n), { timeout: 15_000 }) // the sidebar's badge agrees
  view.unmount()
  return n
}

/** Settings → Calendars, as a user picks a calendar's choice there. */
async function choose(calendar: string, choice: "Hide" | "Plan around it") {
  const view = await openFriday("/settings/calendars")
  const group = await screen.findByRole("group", { name: `${calendar} on your calendar` }, { timeout: 15_000 })
  await view.user.click(within(group).getByRole("button", { name: choice }))
  await waitForSent("settings_set")
  await waitFor(() => expect(view.client.isFetching()).toBe(0), { timeout: 20_000 })
  view.unmount()
}

describe("a calendar you hide", () => {
  it("takes what it sent out of the Inbox and its count at once, and brings it back shown again", async () => {
    const inbox = await friday.q<Inbox>("inbox")
    const advising = inbox.suggestions.find((s) => s.input.title === "Advising appointment")
    expect(advising?.source_kind).toBe("gcal") // a change from one of Alex's Google calendars
    const calendar = advising!.source
    const before = await inboxSays(true)

    await choose(calendar, "Hide")
    const hidden = await inboxSays(false)
    const fromIt = inbox.suggestions.filter((s) => s.source === calendar).length
    expect(hidden).toBe(before - fromIt)
    expect((await friday.q<Inbox>("inbox")).suggestions.some((s) => s.source === calendar)).toBe(false)
    expect((await friday.q<{ suggestions: number }>("status")).suggestions).toBe((await friday.q<Inbox>("inbox")).suggestions.length)

    await choose(calendar, "Plan around it")
    expect(await inboxSays(true)).toBe(before)
  }, 90_000)
})
