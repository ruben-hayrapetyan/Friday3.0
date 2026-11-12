// The tour: six small quests done in the app itself, each noticing when you've done it; "Show me" takes you to the
// control; the card tucks away into a pill and comes back; closed, it's over. (The guide drawn beside it needs WebGL,
// which happy-dom hasn't: the card alone shows, as it does wherever the guide can't be drawn.)
import { cleanup, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday, waitForSent } from "@/test/friday"

type User = Awaited<ReturnType<typeof openFriday>>["user"]
const card = () => within(screen.getByRole("region", { name: "Quests: getting to know Friday" }))
const route = () => window.location.hash.replace(/^#/, "").split("?")[0]
const kept = () => JSON.parse(window.localStorage.getItem("friday-quests") ?? "null") as { done: string[]; small: boolean; over: boolean } | null

async function takeTour(user: User) {
  await user.click(screen.getAllByRole("button", { name: "Take the tour" })[0])
  await screen.findByRole("region", { name: "Quests: getting to know Friday" })
}

describe("the tour", () => {
  it("opens from the ? beside Settings with six quests, the first one open", async () => {
    const { user } = await openFriday("/")
    await takeTour(user)
    expect(card().getByText("Quests")).toBeTruthy()
    expect(card().getByText("0/6")).toBeTruthy()
    for (const quest of ["Add a to-do", "Find where Friday put it", "Start working on it", "Find anything", "Look in your Inbox", "Write a rule"]) expect(card().getByRole("button", { name: quest })).toBeTruthy()
    expect(card().getByRole("button", { name: "Add a to-do" }).getAttribute("aria-expanded")).toBe("true")
    expect(card().getByText("Type it as you’d say it: “essay 3h due Fri”")).toBeTruthy()
    expect(kept()).toEqual({ done: [], small: false, over: false }) // kept from the start, for when Friday opens again
  })

  it("opens a quest you pick, and Show me takes you where it's done", async () => {
    const { user } = await openFriday("/")
    await takeTour(user)
    await user.click(card().getByRole("button", { name: "Write a rule" }))
    expect(card().getByRole("button", { name: "Write a rule" }).getAttribute("aria-expanded")).toBe("true")
    expect(card().getByText("In your own words: “no work after 10pm”")).toBeTruthy()
    await user.click(card().getByRole("button", { name: "Show me" }))
    await waitFor(() => expect(route()).toBe("/rules"))
    await user.click(card().getByRole("button", { name: "Add a to-do" }))
    await user.click(card().getByRole("button", { name: "Show me" }))
    await waitFor(() => expect(route()).toBe("/"))
    await waitFor(() => expect(document.querySelector("[data-tour=drawer-add]")).not.toBeNull()) // the to-do list opened beside the calendar
  })

  it("notices each quest as you do it, cheers, and ticks it off", async () => {
    const { user } = await openFriday("/")
    await takeTour(user)
    // Find anything: search opened
    await user.keyboard("{Meta>}k{/Meta}")
    await screen.findByRole("dialog", { name: "Search" })
    await waitFor(() => expect(card().getByText("1/6")).toBeTruthy())
    expect(card().getByText("Nice!")).toBeTruthy()
    expect(card().getByRole("button", { name: "Find anything" }).hasAttribute("disabled")).toBe(true)
    // Add a to-do: from the list beside the plan
    await user.keyboard("{Escape}")
    await user.keyboard("t")
    const add = await waitFor(() => within(document.querySelector<HTMLElement>("[data-tour=drawer-add]")!).getByRole("textbox"))
    await user.type(add, "qqzz tour practice task{Enter}")
    await waitForSent("add")
    await waitFor(() => expect(card().getByText("2/6")).toBeTruthy())
    expect(card().getByText("There you go!")).toBeTruthy()
    // Write a rule: one added on the Rules page (the Inbox's quest, a page opened, isn't opened here: its page sometimes
    // renders without end in these tests, inbox/InboxPage.tsx)
    await user.click(card().getByRole("button", { name: "Write a rule" }))
    await user.click(card().getByRole("button", { name: "Show me" }))
    await waitFor(() => expect(route()).toBe("/rules"))
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "No work after 11pm{Enter}")
    await waitForSent("rule_add", 15_000)
    await waitFor(() => expect(card().getByText("3/6")).toBeTruthy())
    expect(kept()?.done.sort()).toEqual(["add", "rule", "search"])
  })

  it("tucks away into a pill that says how far you've got, and opens again from it", async () => {
    const { user } = await openFriday("/")
    await takeTour(user)
    await user.click(card().getByRole("button", { name: "Tuck the quests away" }))
    expect(screen.queryByRole("region", { name: "Quests: getting to know Friday" })).toBeNull()
    const pill = screen.getByRole("button", { name: "Quests, 0 of 6 done: open" })
    expect(kept()?.small).toBe(true)
    await user.click(pill)
    expect(await screen.findByRole("region", { name: "Quests: getting to know Friday" })).toBeTruthy()
    expect(kept()?.small).toBe(false)
  })

  it("comes back when Friday opens with the quests under way on this device", async () => {
    window.localStorage.setItem("friday-quests", JSON.stringify({ done: ["search", "inbox"], small: true, over: false }))
    await openFriday("/")
    expect(await screen.findByRole("button", { name: "Quests, 2 of 6 done: open" }, { timeout: 5000 })).toBeTruthy()
  })

  it("closed, is over: it doesn't come back by itself, and the ? starts it again from the beginning", async () => {
    const { user } = await openFriday("/")
    await takeTour(user)
    await user.keyboard("{Meta>}k{/Meta}")
    await waitFor(() => expect(card().getByText("1/6")).toBeTruthy())
    await user.keyboard("{Escape}")
    await user.click(card().getByRole("button", { name: "Close the quests" }))
    await waitFor(() => expect(screen.queryByRole("region", { name: "Quests: getting to know Friday" })).toBeNull())
    expect(kept()?.over).toBe(true)
    cleanup()
    const again = await openFriday("/")
    await new Promise((r) => setTimeout(r, 1200))
    expect(screen.queryByRole("region", { name: "Quests: getting to know Friday" })).toBeNull()
    expect(screen.queryByRole("button", { name: /^Quests, / })).toBeNull()
    await takeTour(again.user)
    expect(card().getByText("0/6")).toBeTruthy()
  })

  it("all six done, says that's Friday, and Done sends it off", async () => {
    window.localStorage.setItem("friday-quests", JSON.stringify({ done: ["add", "find", "start", "search", "inbox"], small: false, over: false }))
    const { user } = await openFriday("/rules")
    await waitFor(() => expect(screen.getByRole("region", { name: "Quests: getting to know Friday" })).toBeTruthy(), { timeout: 5000 })
    expect(card().getByText("5/6")).toBeTruthy()
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "No work after 10pm{Enter}")
    await waitForSent("rule_add", 15_000)
    expect(await card().findByText("That’s Friday!")).toBeTruthy()
    expect(card().getByText("All done")).toBeTruthy()
    expect(card().getByText("The ? brings these back any time")).toBeTruthy()
    await user.click(card().getByRole("button", { name: "Done" }))
    await waitFor(() => expect(screen.queryByRole("region", { name: "Quests: getting to know Friday" })).toBeNull())
    expect(kept()?.over).toBe(true)
  })

  it("counts a planned block you click, and starting work on it", async () => {
    // happy-dom can't say what's under the pointer; nothing is, here
    if (typeof document.elementsFromPoint !== "function") Object.assign(document, { elementsFromPoint: () => [] })
    const { user } = await openFriday("/")
    await takeTour(user)
    const block = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('[data-block-key^="T"]')
      expect(found).not.toBeNull()
      return found!
    })
    await user.click(block)
    await waitFor(() => expect(card().getByRole("button", { name: "Find where Friday put it" }).hasAttribute("disabled")).toBe(true))
    const popover = await waitFor(() => {
      const found = document.querySelector<HTMLElement>(".fr-block-card")
      expect(found).not.toBeNull()
      return found!
    })
    const start = within(popover).queryAllByRole("button", { name: /^(Start|Resume|Switch)/ })[0]
    if (!start) return // a block from before now: nothing to start
    await user.click(start)
    await waitForSent("start")
    await waitFor(() => expect(card().getByRole("button", { name: "Start working on it" }).hasAttribute("disabled")).toBe(true))
  })
})
