// The tour (12 Nov): one stop per page, each saying what it's for; Back, Next, Done, × and Esc. And the ? beside
// Settings: the page dimmed, a label beside each of its controls, the tour a click away. (The guide drawn beside the
// tour needs WebGL, which happy-dom hasn't: the card alone shows, as it does wherever the guide can't be drawn.)
import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { openFriday } from "@/test/friday"
import { STOPS } from "./Tour"

const tour = () => screen.queryByRole("dialog", { name: /^Tour of Friday/ })

// happy-dom lays nothing out (every box is 0 × 0): each element is given a box, as a browser would, so the tour has
// something to ring and the ? something to label; where they go is the unit tests' (Tour.test.ts)
const measure = Element.prototype.getBoundingClientRect
beforeEach(() => {
  Element.prototype.getBoundingClientRect = function () {
    return { left: 300, top: 200, width: 120, height: 32, right: 420, bottom: 232, x: 300, y: 200, toJSON: () => ({}) } as DOMRect
  }
})
afterEach(() => {
  Element.prototype.getBoundingClientRect = measure
})
const card = () => within(tour() as HTMLElement)
const route = () => window.location.hash.replace(/^#/, "").split("?")[0] || "/"

describe("the tour", () => {
  it("goes page by page, opening each one and saying what it's for, with Back and Next", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getAllByRole("button", { name: "What's on this page" })[0])
    await user.click(await screen.findByRole("button", { name: "Take the tour" }))
    expect(await screen.findByRole("dialog", { name: "Tour of Friday: Here's your plan" })).toBeTruthy()
    expect(card().getByText(`1/${STOPS.length}`)).toBeTruthy()
    expect(card().queryByRole("button", { name: "Back" })).toBeNull()
    await user.click(card().getByRole("button", { name: "Next" }))
    expect(card().getByRole("heading", { name: "To-do: what you have to do" })).toBeTruthy()
    expect(card().getByText(/Work is a to-do, not an event/)).toBeTruthy()
    // the page itself, not just its tab (12 Nov: "it should actually navigate to each of the pages")
    await waitFor(() => expect(route()).toBe("/todo"))
    // what it's about is ringed: the page in the sidebar
    await waitFor(() => expect(document.querySelector(".gd-ring")).not.toBeNull())
    await user.click(card().getByRole("button", { name: "Back" }))
    expect(card().getByRole("heading", { name: "Here's your plan" })).toBeTruthy()
    await waitFor(() => expect(route()).toBe("/"))
    await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}")
    expect(card().getByRole("heading", { name: "Rules: how you like your days" })).toBeTruthy()
    expect(card().getByText(/no need to make Breakfast, Lunch or Dinner events/)).toBeTruthy()
    await waitFor(() => expect(route()).toBe("/rules"))
    await user.click(card().getByRole("button", { name: "Next" }))
    await user.click(card().getByRole("button", { name: "Next" }))
    expect(card().getByRole("heading", { name: "That's Friday" })).toBeTruthy()
    await user.click(card().getByRole("button", { name: "Done" }))
    await waitFor(() => expect(tour()).toBeNull())
  })

  it("ends with × or Esc", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getAllByRole("button", { name: "What's on this page" })[0])
    await user.click(await screen.findByRole("button", { name: "Take the tour" }))
    await screen.findByRole("dialog", { name: /^Tour of Friday/ })
    await user.keyboard("{Escape}")
    await waitFor(() => expect(tour()).toBeNull())
  })
})

describe("the ?: what's on this page", () => {
  it("dims the page, numbers its controls and lists what each does; a click outside the list, or Esc, closes it", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getAllByRole("button", { name: "What's on this page" })[0])
    const help = await screen.findByRole("dialog", { name: "What's on this page" })
    const notes = () => within(help).getAllByRole("listitem").map((n) => n.textContent?.replace(/^\d+/, ""))
    await waitFor(() => expect(notes()).toContain("Find anything: to-dos, events, settings (⌘K)"))
    expect(notes()).not.toContain("To-do: everything you have to do") // the sidebar's pages are the tour's
    // the calendar too, once it's drawn: the labels follow the page as it settles
    await waitFor(() => expect(notes().some((n) => /^Click a block to start, finish or move it/.test(n ?? ""))).toBe(true))
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "What's on this page" })).toBeNull())
    await user.click(screen.getAllByRole("button", { name: "What's on this page" })[0])
    await user.click(await screen.findByRole("dialog", { name: "What's on this page" }))
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "What's on this page" })).toBeNull())
  })

  it("labels what's on the page you're on", async () => {
    const { user } = await openFriday("/rules")
    await user.click(screen.getAllByRole("button", { name: "What's on this page" })[0])
    const help = await screen.findByRole("dialog", { name: "What's on this page" })
    expect(within(help).getByText("Type a rule, or a note about you, in your own words")).toBeTruthy()
    expect(within(help).queryByText("Find anything: to-dos, events, settings (⌘K)")).toBeNull() // that's the plan's
  })
})
