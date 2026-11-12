// The to-do drawer beside the plan: opened from the plan's title row, its quick add with what Friday read, the list by
// due, when or tag (sorted as asked), a row ticked off or opened on the To-do page, several picked to change together,
// its left edge dragged wider, and the ways out.
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

/** The plan with the drawer open. */
async function drawer() {
  const f = await openFriday("/")
  await f.user.click(await screen.findByRole("button", { name: "To-do list" }))
  const line = await screen.findByPlaceholderText("Add a to-do")
  const aside = line.closest("aside") as HTMLElement
  return { ...f, aside, line }
}

/** A row in the drawer, by its task's title. */
const rowIn = async (aside: HTMLElement, title: string) =>
  (await within(aside).findAllByText((_, el) => el?.tagName === "SPAN" && (el.textContent ?? "").trim().endsWith(` ${title}`.trimStart()) && !!el.closest('[role="button"]'), {}, { timeout: 10_000 }))[0].closest('[role="button"]') as HTMLElement

const view = (aside: HTMLElement, name: string) => within(aside).getByRole("button", { name })

describe("the to-do drawer", () => {
  it("opens beside the plan on what's due, and closes", async () => {
    const { user, aside } = await drawer()
    expect(within(aside).getByText("To-do")).toBeTruthy()
    expect(view(aside, "Due").getAttribute("aria-pressed")).toBe("true")
    expect(await rowIn(aside, "MATH 1910 Written HW 8")).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByPlaceholderText("Add a to-do")).toBeNull())
  })

  it("adds a to-do from its line, with what Friday read shown as you type", async () => {
    const { user, line, aside } = await drawer()
    await user.type(line, "buy solder #Rocketry due tomorrow ~30m")
    const read = (text: string | RegExp) => within(aside).findByText((_, el) => el?.tagName === "SPAN" && el.childElementCount === 1 && !!(el.textContent ?? "").match(text), {}, { timeout: 5000 })
    expect(await read(/^TagRocketry$/)).toBeTruthy()
    expect(await read(/^Length~30m$/)).toBeTruthy()
    expect(await read(/^Due(Thu|Fri|Sat|Sun|Mon|Tue|Wed|Tomorrow)/)).toBeTruthy()
    await user.keyboard("{Enter}")
    expect((await waitForSent("add")).body).toEqual({ text: "buy solder #Rocketry due tomorrow ~30m" })
    await waitFor(() => expect((line as HTMLInputElement).value).toBe(""))
    await user.type(line, "something else")
    await user.keyboard("{Escape}")
    expect((line as HTMLInputElement).value).toBe("")
  })

  it("lists by when or by tag, sorted as asked, and keeps the view for next time", async () => {
    const { user, aside } = await drawer()
    await user.click(view(aside, "When"))
    expect(window.localStorage.getItem("friday-drawer-view")).toBe("When")
    const sort = within(aside).getByRole("button", { name: "Next up" })
    await user.click(sort)
    await user.click(within(aside).getByRole("radio", { name: "Title" }))
    expect(within(aside).getByRole("button", { name: "Title" })).toBeTruthy()
    await user.click(view(aside, "Tag"))
    expect(await within(aside).findByText("MATH 1910")).toBeTruthy()
    expect(within(aside).getByText("No tag")).toBeTruthy()
    await user.click(view(aside, "Due"))
    expect(within(aside).queryByRole("button", { name: "Title" })).toBeNull()
  })

  it("ticks a task done from its row", async () => {
    const { user, aside } = await drawer()
    const hw = await rowIn(aside, "PHYS 1112 Mastering Physics 9")
    await user.click(within(hw).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toMatchObject({ id: expect.any(Number) })
  })

  it("opens a task on the To-do page with a click, or Enter", async () => {
    const { user, aside } = await drawer()
    await user.click(await rowIn(aside, "MATH 1910 Written HW 8"))
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/todo\?item=\d+$/))
    expect(await screen.findByText("Planned sessions")).toBeTruthy()
  })

  it("opens a task with the keyboard too", async () => {
    const { user, aside } = await drawer()
    ;(await rowIn(aside, "MATH 1910 Written HW 8")).focus()
    await user.keyboard("{Enter}")
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/todo\?item=\d+$/))
  })

  it("picks several with ⌘-click and Shift-click, changes them from its bar of icons, and Escape lets go", async () => {
    const tomorrow = new Date(Date.now() + 86_400_000)
    const day = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`
    await friday.c("add", { title: "Rocket poster", due: `${day}T17:00`, duration_min: 60 })
    const { user, aside } = await drawer()
    await user.keyboard("{Meta>}")
    await user.click(await rowIn(aside, "Rocket poster"))
    await user.click(await rowIn(aside, "MATH 1910 Written HW 8"))
    await user.keyboard("{/Meta}")
    const bar = await screen.findByRole("toolbar", { name: "2 tasks picked" })
    expect(within(bar).getByText(/Drag them onto the calendar or a day · Esc to clear/)).toBeTruthy()
    await user.click(within(bar).getByRole("button", { name: "Kind" }))
    await user.click(within(bar).getByRole("button", { name: "Errand" }))
    expect((await waitForSent("edit")).body).toMatchObject({ preset: "Errand" })
    await user.keyboard("{Shift>}")
    await user.click(await rowIn(aside, "Prep: PHYS 1112 Prelim 2"))
    await user.keyboard("{/Shift}")
    expect(await screen.findByRole("toolbar", { name: /tasks picked/ })).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull())
  })

  it("goes to the full To-do page", async () => {
    const { user, aside } = await drawer()
    await user.click(within(aside).getByRole("button", { name: "Open full to-do" }))
    await waitFor(() => expect(window.location.hash).toBe("#/todo"))
  })

  it("is made wider by dragging its left edge", async () => {
    const { aside } = await drawer()
    const edge = within(aside).getByRole("separator", { name: "Drag to resize" })
    expect(window.localStorage.getItem("friday-drawer-width")).toBeNull()
    fireEvent.pointerDown(edge, { clientX: 1000 })
    fireEvent.pointerMove(window, { clientX: 900 })
    fireEvent.pointerUp(window, { clientX: 900 })
    // 100px further left: 100px wider than the 340 it starts at, and kept for next time.
    expect(window.localStorage.getItem("friday-drawer-width")).toBe("440")
    fireEvent.pointerMove(window, { clientX: 700 })
    expect(window.localStorage.getItem("friday-drawer-width")).toBe("440")
  })
})
