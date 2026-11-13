// The To-do page over Alex's sample: the three lists, the view options (sections, sort, rows, done items), what a row
// changes in place (done, the title, the due, the length), opening a task beside the list, picking several, dragging
// tasks onto another section, and a task found from the calendar.
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { friday, openFriday, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

const TIP = ": click for everything about it, double-click the title to rename"

/** A task's one-line row, by its title. */
const row = (title: string) => screen.findByTitle(`${title}${TIP}`, {}, { timeout: 10_000 })
const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title) as Item
const list = (name: string) => within(screen.getByRole("group", { name: "List" })).getByRole("button", { name })

async function viewOptions(user: Awaited<ReturnType<typeof openFriday>>["user"]) {
  await user.click(screen.getByRole("button", { name: "View options" }))
}

/** What a drag carries, for the row's dragstart and the section's drop. */
function dataTransfer() {
  const data: Record<string, string> = {}
  return {
    data,
    types: [] as string[],
    effectAllowed: "",
    dropEffect: "",
    setData(k: string, v: string) {
      data[k] = v
      this.types.push(k)
    },
    getData: (k: string) => data[k] ?? "",
    setDragImage() {},
  }
}

describe("the To-do page", () => {
  it("opens on Short term, its sections by kind each with an add line, and says how much is open", async () => {
    await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    expect(list("Short term").getAttribute("aria-pressed")).toBe("true")
    for (const section of ["Readings", "Assignments", "Exam prep", "Errands", "Other"]) expect(screen.getByText(section)).toBeTruthy()
    expect(screen.getByText(/^\d+ open, .* left$/)).toBeTruthy()
    for (const hint of ["Add a reading…", "Add an assignment…", "Add exam prep…", "Add an errand…", "Add anything else…"]) expect(screen.getByLabelText(hint)).toBeTruthy()
    // Empty sections say so; exam prep is pointless once late, marked ⏳.
    expect(screen.getAllByText("nothing yet").length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText("Pointless once late").length).toBeGreaterThan(0)
  })

  it("ticks a task done from its row and opens it again with Undo", async () => {
    const { user } = await openFriday("/todo")
    const hw = await row("MATH 1910 Written HW 9")
    await user.click(within(hw).getByRole("checkbox", { name: "Mark done" }))
    const sent = await waitForSent("done")
    const id = (await itemNamed("MATH 1910 Written HW 9")).id
    expect(sent.body).toEqual({ id })
    await waitFor(async () => expect((await itemNamed("MATH 1910 Written HW 9")).status).toBe("done"))
    await user.click(await screen.findByRole("button", { name: "Undo" }))
    await waitForSent("undo")
    await waitFor(async () => expect((await itemNamed("MATH 1910 Written HW 9")).status).toBe("todo"), { timeout: 5000 })
  })

  it("renames a task by double-clicking its title, and Escape keeps the old one", async () => {
    const { user } = await openFriday("/todo")
    const hw = await row("MATH 1910 WebWork 10")
    await user.dblClick(within(hw).getByText("MATH 1910 WebWork 10"))
    const field = screen.getByRole("textbox", { name: "Title" })
    await user.clear(field)
    await user.type(field, "Scratch{Escape}")
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull()
    await user.dblClick(within(await row("MATH 1910 WebWork 10")).getByText("MATH 1910 WebWork 10"))
    const again = screen.getByRole("textbox", { name: "Title" })
    await user.clear(again)
    await user.type(again, "MATH 1910 WebWork ten{Enter}")
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ title: "MATH 1910 WebWork ten" })
    await row("MATH 1910 WebWork ten")
  })

  it("changes a task's due in its row, typed the way you'd say it", async () => {
    const { user } = await openFriday("/todo")
    const hw = await row("MATH 1910 Written HW 10")
    await user.click(within(hw).getByTitle("Due. Click to change"))
    const due = screen.getByRole("textbox", { name: "Due" })
    await user.type(due, "tomorrow")
    expect(await screen.findByText(/Enter to set/)).toBeTruthy()
    await user.keyboard("{Enter}")
    const sent = await waitForSent("edit")
    const { id } = await itemNamed("MATH 1910 Written HW 10")
    expect(sent.body).toMatchObject({ id, due: expect.stringMatching(/T23:59$/) })
    expect(screen.queryByRole("textbox", { name: "Due" })).toBeNull()
  })

  it("changes how long a task takes in its row, and Done closes the editor", async () => {
    const { user } = await openFriday("/todo")
    const hw = await row("MATH 1910 Written HW 11")
    await user.click(within(hw).getByTitle(/to do\. Click to change$/))
    expect(screen.getByText("How long it takes in all")).toBeTruthy()
    const length = screen.getByRole("textbox", { name: "Length" })
    await user.clear(length)
    await user.type(length, "an hour and a half")
    expect(screen.getByText("→ 1h 30m")).toBeTruthy()
    await user.keyboard("{Enter}")
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ duration_min: 90 })
    expect(screen.queryByRole("textbox", { name: "Length" })).toBeNull()
    // The due editor closes on Done, without changing anything.
    await user.click(within(await row("MATH 1910 Written HW 11")).getByTitle("Due. Click to change"))
    await user.click(screen.getByRole("button", { name: "Done" }))
    expect(screen.queryByRole("textbox", { name: "Due" })).toBeNull()
  })

  it("opens a task's detail beside the list with a click, or Enter, and closes it with a second click", async () => {
    const { user } = await openFriday("/todo")
    await user.click(await row("CHEM 2090 lab report 6"))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
    expect(window.location.hash).toMatch(/item=\d+/)
    await user.click(await row("CHEM 2090 lab report 6"))
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
    ;(await row("CHEM 2090 lab report 6")).focus()
    await user.keyboard("{Enter}")
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("picks several with ⌘-click and Shift-click, ⌘A picks all, and Escape lets go", async () => {
    const { user } = await openFriday("/todo")
    await user.click(await row("MATH 1910 Written HW 8"))
    await user.keyboard("{Meta>}")
    await user.click(await row("CHEM 2090 lab report 6"))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
    // ⌘-click a picked one again lets it go.
    await user.keyboard("{Meta>}")
    await user.click(await row("CHEM 2090 lab report 6"))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "1 task picked" })).toBeTruthy()
    await user.keyboard("{Shift>}")
    await user.click(await row("MATH 1910 Written HW 9"))
    await user.keyboard("{/Shift}")
    const toolbar = await screen.findByRole("toolbar", { name: /tasks picked/ })
    expect(Number(/(\d+) tasks/.exec(toolbar.getAttribute("aria-label") ?? "")?.[1])).toBeGreaterThanOrEqual(2)
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull())
    await user.keyboard("{Meta>}a{/Meta}")
    const all = await screen.findByRole("toolbar", { name: /tasks picked/ })
    expect(Number(/(\d+) tasks/.exec(all.getAttribute("aria-label") ?? "")?.[1])).toBeGreaterThan(10)
    await user.click(screen.getByRole("button", { name: "Clear the picked tasks" }))
    expect(screen.queryByRole("toolbar")).toBeNull()
    // A plain click goes back to one task's detail.
    await user.click(await row("MATH 1910 Written HW 8"))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("makes a task another kind when it's dragged onto that section", async () => {
    await openFriday("/todo")
    const hw = await row("PHYS 1112 Mastering Physics 12")
    const dt = dataTransfer()
    fireEvent.dragStart(hw, { dataTransfer: dt })
    const errands = screen.getByText("Errands").closest("section") as HTMLElement
    fireEvent.dragOver(errands, { dataTransfer: dt })
    fireEvent.dragLeave(errands, { dataTransfer: dt, relatedTarget: document.body })
    fireEvent.dragOver(errands, { dataTransfer: dt })
    fireEvent.drop(errands, { dataTransfer: dt })
    const sent = await waitForSent("edit")
    const { id } = await itemNamed("PHYS 1112 Mastering Physics 12")
    expect(sent.body).toEqual({ id, preset: "Errand" })
    await waitFor(async () => expect((await itemNamed("PHYS 1112 Mastering Physics 12")).preset).toBe("Errand"))
  })

  it("moves every picked task when one of them is dragged, said once with one Undo", async () => {
    const { user } = await openFriday("/todo")
    await user.click(await row("PHYS 1112 Mastering Physics 11"))
    await user.keyboard("{Meta>}")
    await user.click(await row("MATH 1910 WebWork 11"))
    await user.keyboard("{/Meta}")
    await screen.findByRole("toolbar", { name: "2 tasks picked" })
    const dt = dataTransfer()
    fireEvent.dragStart(await row("MATH 1910 WebWork 11"), { dataTransfer: dt })
    expect(dt.data["text/x-friday-item"].split(",")).toHaveLength(2)
    fireEvent.drop(screen.getByText("Other").closest("section") as HTMLElement, { dataTransfer: dt })
    expect(await screen.findByText("Moved 2 tasks to Other. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect((await itemNamed("MATH 1910 WebWork 11")).preset).toBeNull())
    await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
    await waitFor(async () => expect((await itemNamed("MATH 1910 WebWork 11")).preset).toBe("Assignment"))
  })

  it("groups by when, with one add line at the top, and by tag, with an add line for each tag", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "By when" }))
    expect(window.localStorage.getItem("friday-todo-group")).toBe("When")
    expect(screen.getByLabelText("Add a to-do…")).toBeTruthy()
    expect(screen.queryByLabelText("Add an assignment…")).toBeNull()
    await user.click(screen.getByRole("button", { name: "By tag" }))
    expect(await screen.findByLabelText("Add to MATH 1910…")).toBeTruthy()
    expect(screen.getByText("No tag")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "By kind" }))
    expect(await screen.findByLabelText("Add an assignment…")).toBeTruthy()
  })

  it("gives a task a tag when it's dragged onto that tag's section", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "By tag" }))
    const dt = dataTransfer()
    fireEvent.dragStart(await row("Laundry"), { dataTransfer: dt })
    const chem = (await screen.findByLabelText("Add to CHEM 2090…")).closest("section") as HTMLElement
    fireEvent.drop(chem, { dataTransfer: dt })
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ area: "CHEM 2090" })
  })

  it("sorts by title, by length and by due, kept for next time", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    const titlesIn = (section: string) =>
      [...(screen.getByText(section).closest("section") as HTMLElement).querySelectorAll("[data-todo-row]")].map((r) => (r.getAttribute("title") ?? "").replace(TIP, ""))
    await user.click(screen.getByRole("radio", { name: /Title/ }))
    expect(screen.getByRole("radio", { name: /Title/ }).getAttribute("aria-checked")).toBe("true")
    const byTitle = titlesIn("Assignments")
    expect(byTitle).toEqual([...byTitle].sort((a, b) => a.localeCompare(b)))
    expect(window.localStorage.getItem("friday-todo-sort")).toBe("Title")
    await user.click(screen.getByRole("radio", { name: /Length/ }))
    expect(titlesIn("Assignments")[0]).toBe("CHEM 2090 lab report 6")
    await user.click(screen.getByRole("radio", { name: /Due date/ }))
    expect(titlesIn("Assignments")[0]).not.toBe("CHEM 2090 lab report 6")
  })

  it("draws two-line rows with progress when asked, which also tick off and open", async () => {
    // how much the sample did depends on the day it's lived to: set to 1h 15m of its 4h
    await friday.c("progress", { id: (await itemNamed("FWS essay draft")).id, share: 0.3125 })
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Two lines" }))
    await waitFor(() => expect(screen.queryByTitle(`MATH 1910 Written HW 8${TIP}`)).toBeNull())
    expect(screen.getAllByText(/^\dh( \d+m)? to do$/).length).toBeGreaterThan(0)
    // its row (the Now dock may show it too, when it's what's on)
    const essay = screen.getAllByText("FWS essay draft").map((t) => t.closest("[data-todo-row]")).find(Boolean) as HTMLElement
    expect(within(essay).getByText("1h 15m of 4h")).toBeTruthy()
    await user.click(essay)
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
    // Enter on a two-line row opens it too (and a second time puts it away).
    essay.focus()
    await user.keyboard("{Enter}")
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
    const laundry = screen.getAllByText("Laundry")[0].closest("[data-todo-row]") as HTMLElement
    await user.click(within(laundry).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: Number(laundry.getAttribute("data-todo-row")) })
    await user.click(screen.getByRole("button", { name: "View options" }))
    await user.click(screen.getByRole("button", { name: "One line" }))
    await row("MATH 1910 Written HW 8")
  })

  it("shows what's done when asked, in its own section, and opens one again", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Show done" }))
    const reopen = (await screen.findAllByRole("checkbox", { name: "Mark not done" }))[0]
    const section = reopen.closest("section") as HTMLElement
    expect(within(section).queryAllByRole("checkbox", { name: "Mark done" })).toHaveLength(0)
    await user.click(reopen)
    await waitForSent("reopen")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Show done" }))
    await waitFor(() => expect(screen.queryAllByRole("checkbox", { name: "Mark not done" })).toHaveLength(0))
  })

  it("names the done section Done", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Show done" }))
    expect(await screen.findByText("Done", { selector: ".fr-mono" })).toBeTruthy()
  })

  it("lists Long term apart, and an empty one says so", async () => {
    const { user } = await openFriday("/todo")
    await row("MATH 1910 Written HW 8")
    await user.click(list("Long term"))
    expect(window.location.hash).toContain("list=Long")
    expect(screen.queryByTitle(`MATH 1910 Written HW 8${TIP}`)).toBeNull()
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "By when" }))
    expect(await screen.findByText(/Nothing left\. Add something above/)).toBeTruthy()
    await user.click(list("Short term"))
    await row("MATH 1910 Written HW 8")
  })

  it("lists every dated piece of work in Due, soonest first, with the now line after the ones past", async () => {
    const yesterday = new Date(Date.now() - 86_400_000)
    const ymd = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`
    await friday.c("add", { title: "Overdue worksheet", preset: "Assignment", due: `${ymd}T12:00`, duration_min: 30 })
    const { user } = await openFriday("/todo?list=Due")
    await row("Overdue worksheet")
    expect(list("Due").getAttribute("aria-pressed")).toBe("true")
    // Meals and habits aren't work with a due.
    expect(screen.queryByTitle(`Breakfast${TIP}`)).toBeNull()
    const rows = [...document.querySelectorAll("[data-todo-row]")]
    expect(rows[0].getAttribute("title")).toBe(`Overdue worksheet${TIP}`)
    // the list's now line (the calendar beside it may draw its own)
    const nows = screen.getAllByRole("separator", { name: "Now" })
    expect(nows.some((now) => rows[0].compareDocumentPosition(now) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    // No sections or sort here: the view options keep only the rows and done.
    await viewOptions(user)
    expect(screen.queryByRole("button", { name: "By kind" })).toBeNull()
    expect(screen.getByRole("button", { name: "Two lines" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "View options" }))
    // A plain click in Due opens the detail, and keeps the list.
    await user.click(await row("Overdue worksheet"))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
    expect(window.location.hash).toContain("list=Due")
    await user.keyboard("{Meta>}")
    await user.click(await row("MATH 1910 Written HW 8"))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
  })

  it("adds a to-do on the Due list's own add line", async () => {
    const { user } = await openFriday("/todo?list=Due")
    await row("MATH 1910 Written HW 8") // the list read first: an add before it loads is read over by that first answer
    const line = screen.getByLabelText("Add a to-do…")
    await user.type(line, "pick up poster due tomorrow{Enter}")
    const sent = await waitForSent("add")
    expect(sent.body).toMatchObject({ text: "pick up poster due tomorrow" })
    expect(within(await row("pick up poster")).getByText("new")).toBeTruthy()
  })

  it("opens a task found from the calendar in the list that holds it, flashed", async () => {
    const made = await friday.c<{ result: { item: Item } }>("add", { title: "Someday telescope", long_term: true })
    const id = made.result.item.id
    await openFriday(`/todo?item=${id}&found=1`)
    await waitFor(() => expect(window.location.hash).toContain("list=Long"))
    const found = await row("Someday telescope")
    await waitFor(() => expect(found.classList.contains("fr-found")).toBe(true))
    await waitFor(() => expect(window.location.hash).not.toContain("found=1"))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("says when the plan finishes a task after it's due, in both kinds of row", async () => {
    const soon = new Date(Date.now() + 3 * 3_600_000)
    const at = `${soon.getFullYear()}-${String(soon.getMonth() + 1).padStart(2, "0")}-${String(soon.getDate()).padStart(2, "0")}T${String(soon.getHours()).padStart(2, "0")}:00`
    await friday.c("add", { title: "Impossible lab writeup", preset: "Assignment", due: at, duration_min: 600, firmness: "hard" })
    await friday.c("add", { title: "Slipping reading", preset: "Reading", due: at, duration_min: 600, firmness: "soft" })
    const { user, client } = await openFriday("/todo")
    const late = async (title: string, tag: RegExp) =>
      waitFor(
        async () => {
          await client.invalidateQueries({ queryKey: ["status"] }) // the plan's answer, which the live updates would bring
          expect(within(await row(title)).getByText(tag)).toBeTruthy()
        },
        { timeout: 20_000, interval: 500 },
      )
    await late("Impossible lab writeup", /late$/)
    await late("Slipping reading", /late$|not planned/)
    await user.click(screen.getByRole("button", { name: "View options" }))
    await user.click(screen.getByRole("button", { name: "Two lines" }))
    // the row, not another place its title shows (a toast, the calendar)
    const two = await waitFor(() => screen.getAllByText("Impossible lab writeup").map((t) => t.closest("[data-todo-row]")).find(Boolean) as HTMLElement)
    expect(within(two).getByText(/late$/)).toBeTruthy()
  }, 40_000)

  it("points to the Inbox when a task is there more than once", async () => {
    await friday.c("add", { title: "MATH 1910 Written HW 8", preset: "Assignment", area: "MATH 1910", due: (await itemNamed("MATH 1910 Written HW 8")).due })
    const { user } = await openFriday("/todo")
    const copies = await screen.findByRole("link", { name: /with copies · In your Inbox/ }, { timeout: 10_000 })
    await user.click(copies)
    await waitFor(() => expect(window.location.hash).toContain("/inbox"))
  })
})
