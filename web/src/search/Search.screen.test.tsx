// Search (⌘K): to-dos, events, projects, pages and actions, filtered as you type, opened with a click or ↑↓ and
// Enter; with nothing matching, Enter adds what you typed as a to-do.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"

type User = Awaited<ReturnType<typeof openFriday>>["user"]
const route = () => window.location.hash.replace(/^#/, "")
const dialog = () => within(screen.getByRole("dialog", { name: "Search" }))

async function search(user: User, text: string) {
  await user.keyboard("{Meta>}k{/Meta}")
  const box = await screen.findByRole("textbox", { name: "Search" })
  await waitFor(() => expect(document.activeElement).toBe(box))
  if (text) await user.type(box, text)
  return box
}

type Item = { id: number; title: string; status: string; when: string; start: string | null }

describe("search", () => {
  it("opens from the plan's button with everything to go to and do, and closes on a click outside", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getByRole("button", { name: "Search (⌘K)" }))
    await screen.findByRole("dialog", { name: "Search" })
    for (const group of ["Go to", "Actions"]) expect(dialog().getByText(group)).toBeTruthy()
    expect(dialog().getByRole("button", { name: /Shove: take time back/ })).toBeTruthy()
    expect(dialog().getByText("↑↓ to move")).toBeTruthy()
    await user.click(screen.getByRole("dialog", { name: "Search" }).previousElementSibling as HTMLElement)
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull())
  })

  it("finds open to-dos by their title, and opens one in the To-do page", async () => {
    const items = await friday.q<Item[]>("items")
    const task = items.find((i) => i.status === "todo" && i.when !== "fixed" && i.title.length > 4)!
    const { user } = await openFriday("/")
    await search(user, task.title.slice(0, 5))
    expect(await dialog().findByText("To-dos", {}, { timeout: 5000 })).toBeTruthy()
    await user.click(dialog().getAllByRole("button", { name: new RegExp(task.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })[0])
    await waitFor(() => expect(route()).toBe(`/todo?item=${task.id}`))
    expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull()
  })

  it("finds calendar events, and opens one in the drawer on its day", async () => {
    const { user } = await openFriday("/todo")
    await search(user, "Lecture")
    expect(await dialog().findByText("Events")).toBeTruthy()
    const hit = dialog().getAllByRole("button").find((b) => /Lecture/.test(b.textContent ?? "") && b.querySelector(".ph-repeat, .ph-calendar-blank"))!
    const title = hit.querySelectorAll("span")[1]?.textContent ?? ""
    await user.click(hit)
    await waitFor(() => expect(route()).toBe("/"))
    await waitFor(() => expect((screen.getByRole("textbox", { name: "Title" }) as HTMLInputElement).value).toBe(title))
  })

  it("Enter opens the first thing it found", async () => {
    const { user } = await openFriday("/")
    await search(user, "Integrations")
    await user.keyboard("{Enter}")
    await waitFor(() => expect(route()).toBe("/settings/integrations"))
  })

  it("finds projects, and opens one", async () => {
    const projects = await friday.q<{ item: { id: number; title: string } }[]>("projects")
    if (!projects.length) return
    const { user } = await openFriday("/")
    await search(user, projects[0].item.title)
    expect(dialog().getByText("Projects")).toBeTruthy()
    await user.click(dialog().getAllByRole("button", { name: /project$/ })[0])
    await waitFor(() => expect(route()).toMatch(/^\/projects\?id=\d+/))
  })

  it("goes to pages and settings by name", async () => {
    const { user } = await openFriday("/")
    await search(user, "repeating")
    await user.click(dialog().getByRole("button", { name: "Repeating" }))
    await waitFor(() => expect(route()).toBe("/settings/repeating"))
    await search(user, "sleep")
    await user.click(dialog().getByRole("button", { name: "Insights → Sleep" }))
    await waitFor(() => expect(route()).toBe("/insights?tab=sleep"))
  })

  it("moves through what it found with ↑ and ↓, and opens it with Enter", async () => {
    const { user } = await openFriday("/")
    await search(user, "insights")
    // Insights, Insights → Sleep, Insights → Meals
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowUp}{ArrowDown}{Enter}")
    await waitFor(() => expect(route()).toBe("/insights?tab=meals"))
  })

  it("with nothing matching, says Enter adds it as a to-do, and does", async () => {
    const { user } = await openFriday("/")
    await search(user, "zqxj buy stamps")
    expect(dialog().getByText("Nothing matches. Press Enter to add it as a to-do.")).toBeTruthy()
    await user.keyboard("{Enter}")
    expect((await waitForSent("add")).body).toEqual({ text: "zqxj buy stamps" })
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull(), { timeout: 10_000 })
    await waitFor(async () => expect((await friday.q<Item[]>("items")).some((i) => /zqxj buy stamps/i.test(i.title))).toBe(true), { timeout: 10_000 })
  })

  it("adds it once when Enter is pressed again while it's being added", async () => {
    // the audit, 12 Nov: a second Enter (or a held one) before the first add answered made the to-do twice
    const { user } = await openFriday("/")
    await search(user, "zqxj post the letter")
    await user.keyboard("{Enter}{Enter}")
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull(), { timeout: 10_000 })
    expect(sent.filter((c) => c.name === "add" && (c.body as { text?: string }).text === "zqxj post the letter")).toHaveLength(1)
  })

  it("with nothing matching, ↓ then Enter still asks the AI", async () => {
    const { user } = await openFriday("/")
    await search(user, "zqxj what should I do")
    await user.keyboard("{ArrowDown}{Enter}")
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull())
    expect(sent.some((c) => c.name === "add")).toBe(false)
  })

  it("runs its actions: Shove, Pace, the brief, late work, other ways, the tour and setup", async () => {
    const { user } = await openFriday("/")
    await search(user, "shove")
    await user.click(dialog().getByRole("button", { name: /Shove: take time back/ }))
    expect(await screen.findByText("Friday moves work out of it, or tells you what would go late.")).toBeTruthy()
    await user.keyboard("{Escape}")
    await search(user, "pace")
    await user.click(dialog().getByRole("button", { name: /Change pace/ }))
    expect(await screen.findByText("How hard Friday pushes for a while. Deadlines hold whatever you pick.")).toBeTruthy()
    await user.keyboard("{Escape}")
    await search(user, "brief")
    await user.click(dialog().getByRole("button", { name: /Morning brief/ }))
    expect(await screen.findByText("Good morning")).toBeTruthy()
    await user.keyboard("{Escape}")
    await search(user, "what gives")
    await user.click(dialog().getByRole("button", { name: /What gives when it can't all fit/ }))
    expect(await screen.findByText(/Everything fits|won’t make it|Working out what could give/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await search(user, "tour")
    await user.click(dialog().getByRole("button", { name: /Take the tour of Friday/ }))
    expect(await screen.findByRole("dialog", { name: /^Tour of Friday/ })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "End the tour" }))
    await search(user, "set up")
    await user.click(dialog().getByRole("button", { name: /Set up Friday/ }))
    expect(await screen.findByRole("heading", { name: "Fit Friday to your week again." })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Close" }))
  })

})
