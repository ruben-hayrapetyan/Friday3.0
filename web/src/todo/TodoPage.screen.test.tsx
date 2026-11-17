// The To-do page over Alex's sample: the three lists, the view options (sections, sort, rows, done items), what a row
// changes in place (done, the title, the due, the length), opening a task beside the list, picking several, dragging
// tasks onto another section, and a task found from the calendar.
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { dur } from "@/lib/format"
import { addDays } from "@/lib/time"
import { friday, openFriday, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

const TIP = ": click for everything about it, double-click the title to rename"

/** A task's one-line row, by its title. */
const row = (title: string) => screen.findByTitle(`${title}${TIP}`, {}, { timeout: 10_000 })
const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title) as Item
/** The open MATH 1910 Written HWs, soonest due first: which ones the sample's three weeks finish early moves with the planner. */
const openHomework = async () =>
  (await items())
    .filter((i) => i.status === "todo" && /^MATH 1910 Written HW \d+$/.test(i.title))
    .sort((a, b) => (a.due ?? "").localeCompare(b.due ?? "") || a.id - b.id)
    .map((i) => i.title)
/** The next homework: open, in Short term, on the Due list; the next assignment if every Written HW is done. */
const nextHomework = async () => (await openHomework())[0] ?? (await openAssignments())[0]
/** The open assignments in Short term, soonest due first, each its own title: for a test that needs a few of them. */
const openWork = async () => {
  const open = (await items()).filter((i) => i.status === "todo" && i.preset === "Assignment" && !i.long_term)
  return open.filter((i) => open.filter((o) => o.title === i.title).length === 1).sort((a, b) => (a.due ?? "~").localeCompare(b.due ?? "~") || a.id - b.id)
}
const openAssignments = async () => (await openWork()).map((i) => i.title)
/** A day as the API writes it, `days` from today on the page's clock (the server's): "2026-11-13". */
const ymd = (days: number) => {
  const d = new Date(Date.now() + days * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
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
    await row(await nextHomework())
    expect(list("Short term").getAttribute("aria-pressed")).toBe("true")
    for (const section of ["Readings", "Assignments", "Exam prep", "Errands", "Other"]) expect(screen.getByText(section)).toBeTruthy()
    expect(screen.getByText(/^\d+ open, .* left$/)).toBeTruthy()
    for (const hint of ["Add a reading…", "Add an assignment…", "Add exam prep…", "Add an errand…", "Add anything else…"]) expect(screen.getByLabelText(hint)).toBeTruthy()
    // Empty sections say so; exam prep is pointless once late, marked ⏳.
    expect(screen.getAllByText("nothing yet").length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText("Pointless once late").length).toBeGreaterThan(0)
  })

  it("ticks a task done from its row and opens it again with Undo", async () => {
    const title = await nextHomework()
    const { id } = await itemNamed(title)
    const { user } = await openFriday("/todo")
    const hw = await row(title)
    await user.click(within(hw).getByRole("checkbox", { name: "Mark done" }))
    const sent = await waitForSent("done")
    expect(sent.body).toEqual({ id })
    await waitFor(async () => expect((await itemNamed(title)).status).toBe("done"))
    await user.click(await screen.findByRole("button", { name: "Undo" }))
    await waitForSent("undo")
    await waitFor(async () => expect((await itemNamed(title)).status).toBe("todo"), { timeout: 5000 })
  })

  it("renames a task by double-clicking its title, and Escape keeps the old one", async () => {
    const title = await nextHomework()
    const { id } = await itemNamed(title)
    const renamed = `${title}, renamed`
    const { user } = await openFriday("/todo")
    const hw = await row(title)
    await user.dblClick(within(hw).getByText(title))
    const field = screen.getByRole("textbox", { name: "Title" })
    await user.clear(field)
    await user.type(field, "Scratch{Escape}")
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull()
    await user.dblClick(within(await row(title)).getByText(title))
    const again = screen.getByRole("textbox", { name: "Title" })
    await user.clear(again)
    await user.type(again, `${renamed}{Enter}`)
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ id, title: renamed })
    await row(renamed)
    await waitFor(async () => expect((await items()).find((i) => i.id === id)?.title).toBe(renamed))
    await friday.c("edit", { id, title }) // its own name again, for the tests after
  })

  it("changes a task's due in its row, typed the way you'd say it", async () => {
    // one not due tomorrow already, so "tomorrow" changes it (17 Nov: the next homework was due tomorrow)
    const { id, title, due: was } = (await openWork()).find((i) => i.due && !i.due.startsWith(ymd(1))) as Item
    const { user } = await openFriday("/todo")
    const hw = await row(title)
    await user.click(within(hw).getByTitle("Due. Click to change"))
    const due = screen.getByRole("textbox", { name: "Due" })
    await user.type(due, "tomorrow")
    expect(await screen.findByText(/Enter to set/)).toBeTruthy()
    await user.keyboard("{Enter}")
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ id, due: `${ymd(1)}T23:59` })
    expect(screen.queryByRole("textbox", { name: "Due" })).toBeNull()
    await waitFor(async () => expect((await itemNamed(title)).due).toBe(`${ymd(1)}T23:59`))
    await friday.c("edit", { id, due: was }) // its own due again, for the tests after
  })

  it("changes how long a task takes in its row, and Done closes the editor", async () => {
    // one with nothing done yet, whose row says how long it takes ("2h to do"), not how far along it is
    const { id, title, duration_min: was } = (await openWork()).find((i) => !i.done_min && i.duration_min !== 90) as Item
    const { user } = await openFriday("/todo")
    const hw = await row(title)
    await user.click(within(hw).getByTitle(/to do\. Click to change$/))
    expect(screen.getByText("How long it takes in all")).toBeTruthy()
    const length = screen.getByRole("textbox", { name: "Length" })
    await user.clear(length)
    await user.type(length, "an hour and a half")
    expect(screen.getByText("→ 1h 30m")).toBeTruthy()
    await user.keyboard("{Enter}")
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ id, duration_min: 90 })
    expect(screen.queryByRole("textbox", { name: "Length" })).toBeNull()
    // The due editor closes on Done, without changing anything.
    await user.click(within(await row(title)).getByTitle("Due. Click to change"))
    await user.click(screen.getByRole("button", { name: "Done" }))
    expect(screen.queryByRole("textbox", { name: "Due" })).toBeNull()
    await waitFor(async () => expect((await itemNamed(title)).duration_min).toBe(90))
    await friday.c("edit", { id, duration_min: was }) // its own length again, for the tests after
  })

  it("opens a task's detail beside the list with a click, or Enter, and closes it with a second click", async () => {
    const [task] = await openWork()
    const { user } = await openFriday("/todo")
    await user.click(await row(task.title))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
    expect(window.location.hash).toContain(`item=${task.id}`)
    await user.click(await row(task.title))
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
    ;(await row(task.title)).focus()
    await user.keyboard("{Enter}")
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("picks several with ⌘-click and Shift-click, ⌘A picks all, and Escape lets go", async () => {
    const [hw, nextHw, other] = await openAssignments()
    const { user } = await openFriday("/todo")
    await user.click(await row(hw))
    await user.keyboard("{Meta>}")
    await user.click(await row(other))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
    // ⌘-click a picked one again lets it go.
    await user.keyboard("{Meta>}")
    await user.click(await row(other))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "1 task picked" })).toBeTruthy()
    await user.keyboard("{Shift>}")
    await user.click(await row(nextHw))
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
    await user.click(await row(hw))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("makes a task another kind when it's dragged onto that section", async () => {
    const { id, title } = (await openWork()).at(-1) as Item
    await openFriday("/todo")
    const hw = await row(title)
    const dt = dataTransfer()
    fireEvent.dragStart(hw, { dataTransfer: dt })
    const errands = screen.getByText("Errands").closest("section") as HTMLElement
    fireEvent.dragOver(errands, { dataTransfer: dt })
    fireEvent.dragLeave(errands, { dataTransfer: dt, relatedTarget: document.body })
    fireEvent.dragOver(errands, { dataTransfer: dt })
    fireEvent.drop(errands, { dataTransfer: dt })
    const sent = await waitForSent("edit")
    expect(sent.body).toEqual({ id, preset: "Errand" })
    await waitFor(async () => expect((await itemNamed(title)).preset).toBe("Errand"))
    await friday.c("edit", { id, preset: "Assignment" }) // an assignment again, for the tests after
  })

  it("moves every picked task when one of them is dragged, said once with one Undo", async () => {
    // two assignments due last, away from the ones the other tests here name
    const [first, second] = (await openAssignments()).slice(-2)
    const { user } = await openFriday("/todo")
    await user.click(await row(first))
    await user.keyboard("{Meta>}")
    await user.click(await row(second))
    await user.keyboard("{/Meta}")
    await screen.findByRole("toolbar", { name: "2 tasks picked" })
    const dt = dataTransfer()
    fireEvent.dragStart(await row(second), { dataTransfer: dt })
    expect(dt.data["text/x-friday-item"].split(",").map(Number).sort()).toEqual([(await itemNamed(first)).id, (await itemNamed(second)).id].sort())
    fireEvent.drop(screen.getByText("Other").closest("section") as HTMLElement, { dataTransfer: dt })
    expect(await screen.findByText("Moved 2 tasks to Other. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect([(await itemNamed(first)).preset, (await itemNamed(second)).preset]).toEqual([null, null]))
    await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
    await waitFor(async () => expect([(await itemNamed(first)).preset, (await itemNamed(second)).preset]).toEqual(["Assignment", "Assignment"]))
  })

  it("groups by when, with one add line at the top, and by tag, with an add line for each tag", async () => {
    const { user } = await openFriday("/todo")
    await row(await nextHomework())
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
    await row(await nextHomework())
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
    await row(await nextHomework())
    await viewOptions(user)
    const titlesIn = (section: string) =>
      [...(screen.getByText(section).closest("section") as HTMLElement).querySelectorAll("[data-todo-row]")].map((r) => (r.getAttribute("title") ?? "").replace(TIP, ""))
    await user.click(screen.getByRole("radio", { name: /Title/ }))
    expect(screen.getByRole("radio", { name: /Title/ }).getAttribute("aria-checked")).toBe("true")
    const byTitle = titlesIn("Assignments")
    expect(byTitle).toEqual([...byTitle].sort((a, b) => a.localeCompare(b)))
    expect(window.localStorage.getItem("friday-todo-sort")).toBe("Title")
    await user.click(screen.getByRole("radio", { name: /Length/ }))
    // the most left first (what's left of each depends on the day the sample is lived to)
    const left = new Map((await items()).filter((i) => i.status === "todo").map((i) => [i.title, i.remaining_min ?? i.duration_min ?? 0]))
    const byLength = titlesIn("Assignments")
    const lengths = byLength.map((t) => left.get(t) ?? 0)
    expect(lengths).toEqual([...lengths].sort((a, b) => b - a))
    expect(new Set(lengths).size).toBeGreaterThan(1)
    await user.click(screen.getByRole("radio", { name: /Due date/ }))
    expect(titlesIn("Assignments")[0]).not.toBe(byLength[0])
  })

  it("draws two-line rows with progress when asked, which also tick off and open", async () => {
    // how much the sample did depends on the day it's lived to: the longest open assignment, set to a quarter done
    const long = (await openWork()).filter((i) => i.duration_min).sort((a, b) => (b.duration_min ?? 0) - (a.duration_min ?? 0))[0]
    const length = long.duration_min as number
    await friday.c("progress", { id: long.id, share: 0.25 })
    const hw = await nextHomework()
    const { user } = await openFriday("/todo")
    await row(hw)
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Two lines" }))
    await waitFor(() => expect(screen.queryByTitle(`${hw}${TIP}`)).toBeNull())
    expect(screen.getAllByText(/^\dh( \d+m)? to do$/).length).toBeGreaterThan(0)
    // its row (the Now dock and the calendar may show its title too)
    const essay = await waitFor(() => {
      const found = document.querySelector<HTMLElement>(`[data-todo-row="${long.id}"]`)
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(within(essay).getByText(long.title)).toBeTruthy()
    expect(within(essay).getByText(`${dur(length / 4)} of ${dur(length)}`)).toBeTruthy()
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
    await row(hw)
  })

  it("shows what's done when asked, in its own section, and opens one again", async () => {
    const { user } = await openFriday("/todo")
    await row(await nextHomework())
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
    await row(await nextHomework())
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "Show done" }))
    expect(await screen.findByText("Done", { selector: ".fr-mono" })).toBeTruthy()
  })

  it("lists Long term apart, and an empty one says so", async () => {
    const hw = await nextHomework()
    const { user } = await openFriday("/todo")
    await row(hw)
    await user.click(list("Long term"))
    expect(window.location.hash).toContain("list=Long")
    expect(screen.queryByTitle(`${hw}${TIP}`)).toBeNull()
    await viewOptions(user)
    await user.click(screen.getByRole("button", { name: "By when" }))
    expect(await screen.findByText(/Nothing left\. Add something above/)).toBeTruthy()
    await user.click(list("Short term"))
    await row(hw)
  })

  it("lists every dated piece of work in Due, soonest first, with the now line after the ones past", async () => {
    // due before anything else still open (17 Nov: the sample left a Laundry of the week before open), and past
    const earliest = (await items()).filter((i) => i.status === "todo" && i.due).map((i) => i.due as string).sort()[0]
    const day = [ymd(-1), addDays(earliest.slice(0, 10), -1)].sort()[0]
    await friday.c("add", { title: "Overdue worksheet", preset: "Assignment", due: `${day}T12:00`, duration_min: 30 })
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
    await user.click(await row(await nextHomework()))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
  })

  it("adds a to-do on the Due list's own add line", async () => {
    const { user } = await openFriday("/todo?list=Due")
    await row(await nextHomework()) // the list read first: an add before it loads is read over by that first answer
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
    const hw = await itemNamed(await nextHomework())
    await friday.c("add", { title: hw.title, preset: "Assignment", area: "MATH 1910", due: hw.due })
    const { user } = await openFriday("/todo")
    const copies = await screen.findByRole("link", { name: /with copies · In your Inbox/ }, { timeout: 10_000 })
    await user.click(copies)
    await waitFor(() => expect(window.location.hash).toContain("/inbox"))
  })
})
