// Shove and Pace over Alex's sample, opened from the Plan menu: Shove takes a stretch of time back (quick picks, for
// some hours, from one time to another, or a part of tomorrow) and says what it cleared; Pace previews how hard Friday
// pushes for a while before you apply it, with the days that go easier or harder every week.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday, sent, waitForSent } from "@/test/friday"

async function openPop(name: "Shove" | "Pace") {
  const view = await openFriday("/")
  await view.user.click(await screen.findByRole("button", { name: "Plan" }))
  await view.user.click(await screen.findByRole("button", { name: new RegExp(`^${name}`) }))
  return view
}

/** After a shove: what it cleared, or the must-dos it would make late. */
const answered = () => waitFor(() => screen.getByText(/^Shoved$|This time holds work that would then be late/), { timeout: 30_000 })

describe("Shove", () => {
  it("offers quick picks, a length, a stretch of any day and parts of tomorrow", async () => {
    await openPop("Shove")
    expect(await screen.findByText("Shove: take time back")).toBeTruthy()
    expect(screen.getByRole("button", { name: /^Next hour/ })).toBeTruthy()
    expect(screen.getByRole("button", { name: /^Rest of today/ })).toBeTruthy()
    for (const part of ["Morning", "Afternoon", "Evening", "All day"]) expect(screen.getByRole("button", { name: part })).toBeTruthy()
    expect(screen.getByText("Fixed events stay. Nothing goes late without asking you first.")).toBeTruthy()
  })

  it("says when a stretch can't be shoved, and shoves one on another day", async () => {
    const { user } = await openPop("Shove")
    const from = await screen.findByRole("textbox", { name: "From" })
    const to = screen.getByRole("textbox", { name: "To" })
    await user.clear(from)
    await user.type(from, "3pm{Tab}")
    await user.clear(to)
    await user.type(to, "2pm{Tab}")
    expect(await screen.findByText("The end comes after the start")).toBeTruthy()
    await user.clear(to)
    await user.type(to, "5pm{Tab}")
    await user.click(screen.getByRole("button", { name: "Which day" }))
    const days = within(screen.getByRole("listbox", { name: "Which day" })).getAllByRole("option")
    expect(days[0].textContent).toBe("Today")
    expect(days[1].textContent).toBe("Tomorrow")
    await user.click(days[2])
    await waitFor(() => expect(screen.queryByText("The end comes after the start")).toBeNull())
    const shoveButtons = screen.getAllByRole("button", { name: "Shove" })
    await user.click(shoveButtons[1])
    const shoved = await waitForSent("shove")
    expect(shoved.body).toMatchObject({ range: expect.stringMatching(/^15:00-17:00 \+\dd$/), decision: "ask" })
    await answered()
  })

  it("shoves for a number of hours, and undoes it", async () => {
    const { user } = await openPop("Shove")
    await screen.findByText("Shove: take time back")
    await user.click(screen.getByRole("button", { name: "More" }))
    await user.click(screen.getByRole("button", { name: "More" }))
    await user.click(screen.getByRole("button", { name: "Less" }))
    expect(screen.getByText("1.5 h")).toBeTruthy()
    await user.click(screen.getAllByRole("button", { name: "Shove" })[0])
    expect((await waitForSent("shove")).body).toEqual({ range: "90m", decision: "ask" })
    const after = await answered()
    if (after.textContent === "Shoved") {
      await user.click(screen.getByRole("button", { name: "Undo" }))
      await waitForSent("undo")
    } else {
      // it would make work late: go back rather than choose
      await user.click(screen.getByRole("button", { name: "Back" }))
      expect(await screen.findByRole("button", { name: /^Next hour/ })).toBeTruthy()
    }
  })

  it("asks before a stretch makes work late, and keeps the must-dos when you say", async () => {
    const { user } = await openPop("Shove")
    await user.click(await screen.findByRole("button", { name: "All day" }))
    expect((await waitForSent("shove")).body).toMatchObject({ range: expect.stringMatching(/^day \w{3}$/), decision: "ask" })
    const after = await answered()
    if (after.textContent === "Shoved") {
      // nothing would be late: it's cleared, and Show me goes to it on the calendar
      await user.click(screen.getByRole("button", { name: "Show me" }))
      await waitFor(() => expect(screen.queryByText("Shoved")).toBeNull())
      return
    }
    expect(screen.getAllByText(/^\+[\d.]+ h late$/).length).toBeGreaterThan(0)
    await user.click(screen.getByRole("button", { name: "Keep must-dos" }))
    expect((await waitForSent("shove")).body).toMatchObject({ decision: "keep_must_dos" })
    expect(await screen.findByText("Shoved", undefined, { timeout: 30_000 })).toBeTruthy()
    // resting the pointer on it keeps it open; Show me goes to the day on the calendar
    await user.hover(screen.getByRole("status"))
    await user.click(screen.getByRole("button", { name: "Show me" }))
    await waitFor(() => expect(screen.queryByText("Shoved")).toBeNull())
  }, 60_000)

  it("shoves the next hour from the quick picks", async () => {
    const { user } = await openPop("Shove")
    await user.click(await screen.findByRole("button", { name: /^Next hour/ }))
    expect((await waitForSent("shove")).body).toEqual({ range: "1h", decision: "ask" })
    const after = await answered()
    if (after.textContent !== "Shoved") {
      await user.click(screen.getByRole("button", { name: "Shove anyway" }))
      expect((await waitForSent("shove")).body).toMatchObject({ decision: "shove_anyway" })
    }
  }, 60_000)
})

describe("Pace", () => {
  /** The Pace panel, apart from the rest of the page. */
  const pace = () => within(screen.getByText("How hard Friday pushes for a while. Deadlines hold whatever you pick.").closest(".fr-float") as HTMLElement)

  it("previews a pace for a while, and applies it", async () => {
    const { user } = await openPop("Pace")
    expect(await screen.findByText("How hard Friday pushes for a while. Deadlines hold whatever you pick.")).toBeTruthy()
    expect(screen.getByText("Your usual week.")).toBeTruthy()
    expect(screen.getByText("Pick a pace to preview what changes.")).toBeTruthy()
    expect((pace().getByRole("button", { name: "Apply pace" }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(pace().getByRole("button", { name: "Easy" }))
    expect(screen.getByText("Sick or tired. Lighter days, side projects pause.")).toBeTruthy()
    await user.click(pace().getByRole("button", { name: "3 days" }))
    // the preview is the same command, asked without making it
    await waitFor(() => expect(screen.queryByText("Working out the next two weeks…")).toBeNull(), { timeout: 30_000 })
    const before = sent.filter((s) => s.name === "pace").length
    expect(before).toBeGreaterThan(0)
    await user.click(pace().getByRole("button", { name: "Apply pace" }))
    await waitFor(() => expect(sent.filter((s) => s.name === "pace").length).toBe(before + 1))
    expect(sent.filter((s) => s.name === "pace").at(-1)?.body).toEqual({ name: "Easy", for_days: 3 })
    await waitFor(() => expect(screen.queryByText("Apply pace")).toBeNull())
  }, 60_000)

  it("shows the week's paces, steps a day, and closes on Cancel", async () => {
    const { user } = await openPop("Pace")
    await screen.findByText("Every week")
    await user.click(pace().getByRole("button", { name: /^Sun/ }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "pace", value: { weekly: { sun: expect.any(String) } } })
    await user.click(pace().getByRole("button", { name: "Push" }))
    expect(screen.getByText("Motivated. Fuller days, more growth.")).toBeTruthy()
    await user.click(pace().getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByText("Every week")).toBeNull())
  })
})
