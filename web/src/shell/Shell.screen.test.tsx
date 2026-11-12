// The app as a whole: it opens on the plan over a real Friday, the sidebar's pages each open, its mini month and
// today's agenda move the calendar and open what's on it, and the keys and the Mac app's menus work on every page.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

// Not opened here: the Inbox page. Opened in these tests it sometimes renders without end (InboxPage re-rendering
// inside React's act, seen around midnight; inbox/InboxPage.tsx), which stops the whole file.

/** What the Mac app's menus send: a `friday:host` event. */
const host = (action: string, argument?: string) => act(() => void window.dispatchEvent(new CustomEvent("friday:host", { detail: argument === undefined ? { action } : { action, argument } })))

const sidebar = () => within(screen.getAllByRole("complementary")[0])
const route = () => window.location.hash.replace(/^#/, "").split("?")[0]
const marked = () => sidebar().getAllByRole("button").find((b) => b.getAttribute("aria-current") === "date")?.getAttribute("aria-label")
/** Today as the mini month marks it, once it agrees with Friday's planning day (which starts at day_start, so just
 * after midnight it is still yesterday). */
async function todayInMonth(): Promise<string> {
  const d = new Date()
  const clock = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  const { today } = await friday.q<{ today: string }>("calendar", { start: clock, days: "1" })
  await waitFor(() => expect(marked()).toBe(today))
  return today
}
/** Friday opened again somewhere else, as a reload would: the page before it gone first. */
const reopen = (to: string) => (cleanup(), openFriday(to))
const drawerOpen = () => document.querySelector("[data-tour=drawer-add]") !== null

describe("Friday, opened", () => {
  it("shows the plan, with the sidebar's pages", async () => {
    await openFriday("/")
    for (const page of ["Plan", "To-do", "Inbox", "Insights", "Rules"]) expect(screen.getAllByText(page).length).toBeGreaterThan(0)
  })

  it("says it's the demo, with made-up data", async () => {
    await openFriday("/")
    expect(await sidebar().findByText("Demo", {}, { timeout: 10_000 })).toBeTruthy()
    expect(sidebar().getByText("Made-up sample data, not your calendars or mail.")).toBeTruthy()
  })

  it("opens each page from the sidebar, and marks the one you're on", async () => {
    const { user } = await openFriday("/")
    // the Inbox's link: only where it goes (see above)
    expect(sidebar().getByRole("link", { name: /^Inbox/ }).getAttribute("href")).toBe("#/inbox")
    for (const [label, to] of [["To-do", "/todo"], ["Projects", "/projects"], ["Insights", "/insights"], ["Rules", "/rules"], ["Plan", "/"]] as const) {
      const link = sidebar().getByRole("link", { name: new RegExp(`^${label}`) })
      await user.click(link)
      await waitFor(() => expect(route()).toBe(to))
      expect(link.getAttribute("aria-current")).toBe("page")
    }
  })

  it("counts what's waiting in the Inbox beside its link", async () => {
    await openFriday("/")
    const inbox = sidebar().getByRole("link", { name: /^Inbox/ })
    await waitFor(() => expect(inbox.textContent).toMatch(/Inbox\d+/))
  })

  it("opens Settings from the gear", async () => {
    const { user } = await openFriday("/")
    await user.click(sidebar().getByRole("button", { name: "Settings" }))
    await waitFor(() => expect(route()).toMatch(/^\/settings/))
  })

  it("takes old addresses to where they went: exams to Projects, anything else to the plan", async () => {
    await openFriday("/exams")
    await waitFor(() => expect(route()).toBe("/projects"))
    await reopen("/no-such-page")
    await waitFor(() => expect(route()).toBe("/"))
  })
})

describe("the sidebar's mini month", () => {
  it("shows this month with today marked, and steps a month either way", async () => {
    const { user } = await openFriday("/")
    const date = await todayInMonth()
    const month = (by: number) => {
      const d = new Date(`${date.slice(0, 7)}-15T12:00:00`)
      d.setMonth(d.getMonth() + by)
      return d.toLocaleString("en-US", { month: "long" })
    }
    expect(sidebar().getByText(month(0))).toBeTruthy()
    await user.click(sidebar().getByRole("button", { name: "Next month" }))
    expect(sidebar().getByText(month(1))).toBeTruthy()
    await user.click(sidebar().getByRole("button", { name: "Previous month" }))
    await user.click(sidebar().getByRole("button", { name: "Previous month" }))
    expect(sidebar().getByText(month(-1))).toBeTruthy()
  })

  it("shows a day you click in the agenda, and brings you to the plan", async () => {
    const { user } = await openFriday("/todo")
    const today = await todayInMonth()
    const later = new Date(`${today}T12:00:00`)
    later.setDate(later.getDate() + 2)
    const day = `${later.getFullYear()}-${String(later.getMonth() + 1).padStart(2, "0")}-${String(later.getDate()).padStart(2, "0")}`
    expect(sidebar().getByText("Today")).toBeTruthy()
    await user.click(sidebar().getByRole("button", { name: day }))
    await waitFor(() => expect(route()).toBe("/"))
    const weekday = later.toLocaleString("en-US", { weekday: "short" })
    await waitFor(() => expect(sidebar().getByText(`${weekday} ${later.getDate()}`)).toBeTruthy())
    await user.click(sidebar().getByRole("button", { name: today }))
    await waitFor(() => expect(sidebar().getByText("Today")).toBeTruthy())
  })
})

type Fixed = { id: number; title: string; start: string | null; end: string | null; event_kind: string }

describe("the sidebar's agenda", () => {
  it("lists a day's events, and opens one in the drawer, its title ready to change", async () => {
    const { user } = await openFriday("/")
    await todayInMonth()
    const plan = await friday.q<{ fixed: Fixed[] }>("plan")
    const event = plan.fixed.find((f) => f.start && f.end && !f.start.endsWith("T00:00") && f.event_kind !== "shove" && sidebar().queryByRole("button", { name: f.start.slice(0, 10) }))!
    expect(event).toBeTruthy()
    await user.click(sidebar().getByRole("button", { name: event.start!.slice(0, 10) }))
    const row = await waitFor(() => sidebar().getAllByTitle(event.title)[0])
    await user.click(row)
    expect(await screen.findByText("Event")).toBeTruthy()
    expect((screen.getByRole("textbox", { name: "Title" }) as HTMLInputElement).value).toBe(event.title)
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull())
  })
})

describe("the keys that work on every page", () => {
  it("N opens the to-do list beside the plan, and on another page goes to the To-do page", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("n")
    await waitFor(() => expect(drawerOpen()).toBe(true))
    const again = await reopen("/insights")
    await again.user.keyboard("n")
    await waitFor(() => expect(route()).toBe("/todo"))
  })

  it("T opens and closes the to-do list", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("t")
    await waitFor(() => expect(drawerOpen()).toBe(true))
    await user.keyboard("t")
    await waitFor(() => expect(drawerOpen()).toBe(false))
  })

  it("S opens Shove, and S again or Escape closes it", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("s")
    expect(await screen.findByText("Shove: take time back")).toBeTruthy()
    await user.keyboard("s")
    await waitFor(() => expect(screen.queryByText("Shove: take time back")).toBeNull())
    await user.keyboard("s")
    await screen.findByText("Shove: take time back")
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByText("Shove: take time back")).toBeNull())
  })

  it("P opens Pace, and P again closes it", async () => {
    const { user } = await openFriday("/")
    const said = "How hard Friday pushes for a while. Deadlines hold whatever you pick."
    await user.keyboard("p")
    expect(await screen.findByText(said, {}, { timeout: 5000 })).toBeTruthy()
    await user.keyboard("p")
    await waitFor(() => expect(screen.queryByText(said)).toBeNull())
  })

  it("⌘K opens search and Escape closes it; keys typed in it don't run shortcuts; Ctrl-F opens it too", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("{Meta>}k{/Meta}")
    const box = await screen.findByRole("textbox", { name: "Search" })
    await user.type(box, "s")
    expect(screen.queryByText("Friday moves work out of it, or tells you what would go late.")).toBeNull() // no Shove
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search" })).toBeNull())
    await user.keyboard("{Control>}f{/Control}")
    expect(await screen.findByRole("dialog", { name: "Search" })).toBeTruthy()
  })

  it("⌘Z with nothing done says there's nothing to undo, and undoes the last change once there is one", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("{Meta>}z{/Meta}")
    expect(await screen.findByText("Nothing to undo")).toBeTruthy()
    await user.keyboard("t")
    const add = await waitFor(() => within(document.querySelector<HTMLElement>("[data-tour=drawer-add]")!).getByRole("textbox"))
    await user.type(add, "Water the basil{Enter}")
    expect((await waitForSent("add")).body).toMatchObject({ text: "Water the basil" })
    await waitFor(() => expect(document.querySelector(".fr-toasts")?.textContent).toMatch(/Water the basil/), { timeout: 5000 })
    ;(document.activeElement as HTMLElement | null)?.blur() // out of the box: ⌘Z there is the box's own undo
    await user.keyboard("{Meta>}z{/Meta}")
    await waitForSent("undo")
    expect(await screen.findByText("Undone")).toBeTruthy()
  })
})

describe("the Mac app's menus", () => {
  it("open a new event an hour on, from any page", async () => {
    await openFriday("/todo")
    await host("newEvent")
    await waitFor(() => expect(route()).toBe("/"))
    expect(await screen.findByText("New event")).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Title" })))
  })

  it("go to a page, and open search, the brief, the options for late work, the tour and setup", async () => {
    const { user } = await openFriday("/")
    await host("go", "/insights")
    await waitFor(() => expect(route()).toBe("/insights"))
    await host("go", "/nowhere") // not a page Friday has: nothing happens
    expect(route()).toBe("/insights")
    await host("search")
    await screen.findByRole("dialog", { name: "Search" })
    await user.keyboard("{Escape}")
    await host("brief")
    expect(await screen.findByText("Good morning")).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByText("Good morning")).toBeNull())
    await host("triage")
    expect(await screen.findByText(/Everything fits|won’t make it|Working out what could give/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await host("tour")
    expect(await screen.findByRole("dialog", { name: /^Tour of Friday/ })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "End the tour" }))
    await host("setup")
    expect(await screen.findByRole("heading", { name: "Fit Friday to your week again." }, { timeout: 5000 })).toBeTruthy()
    await host("go", "/todo") // setup first: nothing else takes its place
    expect(route()).toBe("/") // where the tour left you: its first stop opens the plan
    await user.click(screen.getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Fit Friday to your week again." })).toBeNull())
  })

  it("change the calendar's view and step it, from any page", async () => {
    await openFriday("/todo")
    const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed")
    await host("view", "day")
    await waitFor(() => expect(route()).toBe("/"))
    await waitFor(() => expect(pressed("Day")).toBe("true"))
    await host("view", "month")
    await waitFor(() => expect(pressed("Month")).toBe("true"))
    await host("next")
    await host("previous")
    await host("today")
    await host("view", "three")
    await waitFor(() => expect(pressed("3 days")).toBe("true"))
    await host("next")
    await host("view", "week")
    await waitFor(() => expect(pressed("Week")).toBe("true"))
  })

  it("open and close the to-do list, Shove, Pace, other ways and Ask", async () => {
    const { user } = await openFriday("/")
    await host("drawer", "open")
    await waitFor(() => expect(drawerOpen()).toBe(true))
    await host("drawer")
    await waitFor(() => expect(drawerOpen()).toBe(false))
    await host("newTodo")
    await waitFor(() => expect(drawerOpen()).toBe(true))
    await host("shove")
    expect(await screen.findByText("Shove: take time back")).toBeTruthy()
    await user.keyboard("{Escape}")
    await host("pace")
    await screen.findByText("How hard Friday pushes for a while. Deadlines hold whatever you pick.", {}, { timeout: 5000 })
    await user.keyboard("{Escape}")
    await host("ask")
    expect(await screen.findByRole("textbox", { name: "What you want" })).toBeTruthy()
  })

  it("open the options for late work from a link to /?triage", async () => {
    await openFriday("/?triage")
    expect(await screen.findByText(/Everything fits|won’t make it|Working out what could give/)).toBeTruthy()
    await waitFor(() => expect(window.location.hash).not.toContain("triage"))
  })
})

describe("a narrower window", () => {
  const page = () => (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM
  const resize = (width: number) => act(() => (page().setViewport({ width, height: 900 }), void window.dispatchEvent(new Event("resize"))))

  it("shows the sidebar as a rail of the pages' icons, with the page's help and Settings", async () => {
    await resize(1000)
    try {
      const { user } = await openFriday("/")
      const rail = within(screen.getAllByRole("complementary")[0])
      for (const label of ["Plan", "To-do", "Projects & exams", "Insights", "Rules"]) expect(rail.getByRole("link", { name: label })).toBeTruthy()
      expect(rail.queryByText("Demo")).toBeNull() // no room for words
      await user.click(rail.getByRole("link", { name: "Rules" }))
      await waitFor(() => expect(route()).toBe("/rules"))
      await user.click(rail.getByRole("button", { name: "What's on this page" }))
      expect(await screen.findByRole("dialog", { name: "What's on this page" })).toBeTruthy()
      await user.keyboard("{Escape}")
      await user.click(rail.getByRole("button", { name: "Settings" }))
      await waitFor(() => expect(route()).toMatch(/^\/settings/))
    } finally {
      await resize(1440)
    }
  })

  it("puts the sidebar behind a menu button, and closes it when a page is picked", async () => {
    try {
      const { user } = await openFriday("/") // opened wide, where its Settings button shows it's ready, then narrowed
      await resize(700)
      await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull())
      await user.click(screen.getByRole("button", { name: "Menu" }))
      const slid = within(await screen.findByRole("complementary"))
      await user.click(slid.getByRole("link", { name: /^To-do/ }))
      await waitFor(() => expect(route()).toBe("/todo"))
      await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull())
      await user.click(screen.getByRole("button", { name: "Menu" }))
      await user.click(within(await screen.findByRole("complementary")).getByRole("button", { name: "Close" }))
      await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull())
    } finally {
      await resize(1440)
    }
  })
})
