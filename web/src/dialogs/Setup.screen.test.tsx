// Setup's questions (not the town drawn behind them: happy-dom has no WebGL, so the box shows on its own): opened
// again from search or Settings, walked through from getting up to going to bed, each answer picked the way it's
// asked, and all of them saved together at the end; or one question alone, saved by itself.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type User = Awaited<ReturnType<typeof openFriday>>["user"]
const title = (name: string) => screen.findByRole("heading", { name }, { timeout: 5000 })
const next = (user: User) => user.click(screen.getByRole("button", { name: /^(Next stop|Start walking|Continue|Start planning)$/ }))
const radio = (group: string, name: RegExp | string) => within(screen.getByRole("radiogroup", { name: group })).getByRole("radio", { name })

async function openSetup(user: User) {
  await user.keyboard("{Meta>}k{/Meta}")
  await user.type(await screen.findByRole("textbox", { name: "Search" }), "set up")
  await user.click(await screen.findByRole("button", { name: /^Set up Friday/ }))
  await title("Fit Friday to your week again.")
}

/** A slider moved with its keys, as you would without a mouse. */
async function slide(user: User, name: string, keys: string) {
  const bar = screen.getByRole("slider", { name })
  bar.focus()
  await user.keyboard(keys)
  return bar
}

describe("Setup, all of it again", () => {
  it("opens on your answers, counts its steps, and closes with Close or Escape", async () => {
    const { user } = await openFriday("/")
    await openSetup(user)
    expect(screen.getByText("Your answers are filled in: change what's different.")).toBeTruthy()
    expect(screen.getByRole("list", { name: /^Step 1 of \d+$/ })).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Skip: keep Friday's guesses" })).toBeNull() // only the first time
    await user.click(screen.getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Fit Friday to your week again." })).toBeNull())
    await openSetup(user)
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Fit Friday to your week again." })).toBeNull())
  })

  it("goes on with Return, and back with Back", async () => {
    const { user } = await openFriday("/")
    await openSetup(user)
    ;(document.activeElement as HTMLElement | null)?.blur()
    fireEvent.keyDown(document.body, { key: "Enter" })
    expect(await title("Are you in school?")).toBeTruthy()
    expect(screen.getByRole("list", { name: /^Step 2 of/ })).toBeTruthy()
    await next(user)
    expect(await title("When do you usually get up?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(await title("Are you in school?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(await title("Fit Friday to your week again.")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Close" }))
  })

  it("walks the week, each question answered its own way, and saves every answer together at the end", async () => {
    const { user } = await openFriday("/")
    await openSetup(user)
    await next(user)

    await title("Are you in school?")
    await user.click(radio("In school", /^No/))
    expect(radio("In school", /^No/).getAttribute("aria-checked")).toBe("true")
    await next(user)

    await title("When do you usually get up?")
    await user.click(radio("Up at: the usual times", "8am"))
    expect(radio("Up at: the usual times", "8am").getAttribute("aria-checked")).toBe("true")
    await user.click(radio("Up at on weekends", "Same"))
    expect(radio("Up at on weekends", "Same").getAttribute("aria-checked")).toBe("true")
    await user.click(radio("Up at on weekends", "Later")) // an hour and a half later than weekdays: 9:30
    await user.click(screen.getByRole("button", { name: "Up at on weekends, a quarter hour later" })) // 9:45
    await next(user)

    await title("How much work fits in a normal day?")
    const normal = await slide(user, "On a normal day", "{Home}{PageUp}{PageUp}{PageUp}{PageUp}{PageUp}{PageUp}{ArrowRight}{ArrowRight}")
    expect(normal.getAttribute("aria-valuenow")).toBe("8")
    await slide(user, "On a normal day", "{ArrowLeft}")
    expect(screen.getByRole("slider", { name: "On a normal day" }).getAttribute("aria-valuetext")).toBe("7.5h")
    await user.click(screen.getByRole("button", { name: "Type an amount" }))
    const typed = screen.getByRole("textbox", { name: "A normal day, typed" })
    await user.clear(typed)
    await user.type(typed, "nonsense")
    expect(screen.getByText("Type it like 6.5h or 90 min")).toBeTruthy()
    await user.clear(typed)
    await user.type(typed, "30h")
    expect(screen.getByText("Between 1h and 16h")).toBeTruthy()
    await user.clear(typed)
    await user.type(typed, "7h")
    expect(screen.getByRole("slider", { name: "On a normal day" }).getAttribute("aria-valuenow")).toBe("7")
    await next(user)

    await title("And when deadlines pile up?")
    await slide(user, "At most, on a heavy day", "{End}")
    expect(screen.getByRole("slider", { name: "At most, on a heavy day" }).getAttribute("aria-valuenow")).toBe("16")
    await next(user)

    await title("How long can you work in one go?")
    await user.click(radio("Longest stretch", /^2 hours/))
    await user.click(screen.getByRole("button", { name: "Another length" }))
    expect(screen.getByRole("textbox", { name: "Longest stretch, typed" })).toBeTruthy()
    await next(user)

    await title("An essay's due Friday at 5pm. When do you want it done?")
    expect(screen.getByText("Exam prep always goes in the days just before the exam.")).toBeTruthy()
    radio("Finish work", /^A day early/).focus()
    await user.keyboard("{ArrowDown}") // the arrows move between the cards, as between radio buttons
    expect(radio("Finish work", /^2 days early/).getAttribute("aria-checked")).toBe("true")
    await next(user)

    await title("How much of each evening stays yours?")
    await slide(user, "Of each weekday evening", "{Home}")
    expect(screen.getByRole("slider", { name: "Of each weekday evening" }).getAttribute("aria-valuetext")).toBe("None")
    expect(screen.queryByRole("radiogroup", { name: "Evenings start at" })).toBeNull()
    await slide(user, "Of each weekday evening", "{End}")
    expect(screen.getByRole("slider", { name: "Of each weekday evening" }).getAttribute("aria-valuetext")).toBe("All of it")
    await user.click(radio("Evenings start at", "7pm"))
    await next(user)

    await title("When do you go to bed?")
    expect(screen.getByText("Friday never plans anything while you sleep.")).toBeTruthy()
    await user.click(radio("Bed at: the usual times", "11pm")) // weekends were the same: they move with it
    expect(radio("Bed at on weekends", "Same").getAttribute("aria-checked")).toBe("true")
    await next(user)

    await title("And of each weekend day?")
    await slide(user, "Of each weekend day", "{Home}")
    await next(user)

    await title("Want a morning brief?")
    expect(screen.getByLabelText("An example morning brief")).toBeTruthy()
    await user.click(radio("Morning brief", /^Yes, every morning/))
    await user.click(radio("Morning brief", /^No thanks/)) // kept off: it would open by itself on the next morning's tests
    await next(user)

    await title("Which AI should Friday read with?")
    await next(user)
    await title("Where are your classes and deadlines now?")
    expect(screen.getByText("Syllabus")).toBeTruthy()
    expect(screen.getByText("A calendar link")).toBeTruthy()
    await next(user)

    await title("What should Friday do with each calendar?")
    const setup = await friday.q<{ answers: { calendars: { name: string }[] } }>("setup")
    const first = setup.answers.calendars[0].name
    await user.click(radio(`${first} on your calendar`, "Hide"))
    expect(radio(`${first} on your calendar`, "Hide").getAttribute("aria-checked")).toBe("true")
    await next(user)

    await title("Here's your week.")
    for (const [label, value] of [["Up", "8am"], ["Bed", "11pm"], ["Work", "7h, up to 16h"], ["Focus", "2h"], ["Done", "2 days early"], ["Evenings free", "from 7pm"], ["Weekends free", "none"], ["Morning brief", "no"], ["In school", "no"]])
      expect(screen.getByRole("button", { name: `${label} ${value}` })).toBeTruthy()
    expect(screen.getByText("Weekdays")).toBeTruthy()
    expect(screen.getByText("Weekends")).toBeTruthy()
    await next(user)

    await title("Ready when you are.")
    await user.click(screen.getByRole("button", { name: "Start planning" }))
    const sent = await waitForSent("setup_save")
    expect(sent.body).toMatchObject({
      school: false,
      wake: "08:00",
      weekend_wake: "09:45",
      normal_hours: 7,
      most_hours: 16,
      focus_hours: 2,
      finish_early_days: 2,
      evening_free: 5,
      evening_from: "19:00",
      bedtime: "23:00",
      weekend_bedtime: "23:00",
      weekend_free: 0,
      brief: false,
    })
    expect((sent.body as { calendars: { name: string; shown: boolean }[] }).calendars.find((c) => c.name === first)).toMatchObject({ shown: false })
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Ready when you are." })).toBeNull())
    const saved = await friday.q<{ answers: { wake: string; school: boolean } }>("setup")
    expect(saved.answers).toMatchObject({ wake: "08:00", school: false })
  })

  it("your answers at the end each go back to where they were asked", async () => {
    const { user } = await openFriday("/")
    await openSetup(user)
    const steps = Number(/of (\d+)/.exec(screen.getByRole("list", { name: /^Step/ }).getAttribute("aria-label")!)![1])
    for (let i = 0; i < steps - 2; i++) await next(user)
    await title("Here's your week.")
    await user.click(screen.getByRole("button", { name: /^Focus / }))
    expect(await title("How long can you work in one go?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Close" }))
  })
})

describe("Setup, one answer alone", () => {
  it("opens from Settings at that question, and saves it by itself", async () => {
    const { user } = await openFriday("/settings")
    await user.click(await screen.findByRole("button", { name: /Change a Setup answer/ }))
    const menu = screen.getByRole("menu")
    for (const label of ["In school or not", "When you get up", "Free weekends", "The morning brief"]) expect(within(menu).getByRole("menuitem", { name: label })).toBeTruthy()
    await user.click(within(menu).getByRole("menuitem", { name: "Longest stretch of work" }))
    expect(await title("How long can you work in one go?")).toBeTruthy()
    expect(screen.queryByRole("list", { name: /^Step/ })).toBeNull() // no steps: just this question
    await user.click(radio("Longest stretch", /^An hour/))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect((await waitForSent("setup_save")).body).toMatchObject({ focus_hours: 1 })
    await waitFor(() => expect(screen.queryByRole("heading", { name: "How long can you work in one go?" })).toBeNull())
  })

  it("Cancel leaves the answer as it was", async () => {
    const { user } = await openFriday("/settings")
    await user.click(await screen.findByRole("button", { name: /Change a Setup answer/ }))
    await user.click(screen.getByRole("menuitem", { name: "The morning brief" }))
    await title("Want a morning brief?")
    await user.click(radio("Morning brief", /^No thanks/))
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Want a morning brief?" })).toBeNull())
    cleanup()
    const { user: again } = await openFriday("/settings")
    await again.click(await screen.findByRole("button", { name: /Change a Setup answer/ }, { timeout: 5000 }))
    await again.click(screen.getByRole("menuitem", { name: "All of Setup’s questions, in order" }))
    expect(await title("Fit Friday to your week again.")).toBeTruthy()
  })
})

describe("the week it shows at the end", () => {
  // 13 Nov, a client: with an early wake and a late bed, "Up 6am" and "Bed 2am" left the day bars' box; they lean in
  // at the ends now (setupWeek.ts underBar). The bar spans 6am to 2am, so these are its two ends.
  it("keeps the Up and Bed times inside the day bars at a 6am wake and a 2am bed", async () => {
    const { user } = await openFriday("/")
    await openSetup(user)
    for (let step = 0; step < 30; step++) {
      const heading = (await screen.findAllByRole("heading")).map((h) => h.textContent ?? "").find((t) => /\?|week/.test(t)) ?? ""
      if (heading.startsWith("Here's your week.")) break
      if (heading.startsWith("When do you usually get up?")) {
        await user.click(radio("Up at: the usual times", "6:30am"))
        await user.click(screen.getByRole("button", { name: "Up at, a quarter hour earlier" }))
        await user.click(screen.getByRole("button", { name: "Up at, a quarter hour earlier" }))
      }
      if (heading.startsWith("When do you go to bed?")) {
        await user.click(radio("Bed at: the usual times", "1am"))
        for (let k = 0; k < 4; k++) await user.click(screen.getByRole("button", { name: "Bed at, a quarter hour later" }))
      }
      await next(user)
      await waitFor(() => expect(screen.getAllByRole("heading").map((h) => h.textContent).join()).not.toBe(heading))
    }
    expect(await title("Here's your week.")).toBeTruthy()
    const ups = screen.getAllByText("Up 6am")
    const beds = screen.getAllByText("Bed 2am")
    for (const up of ups) expect([up.style.left, up.style.translate]).toEqual(["0%", "0% 0"]) // starts at the left edge
    for (const bed of beds) expect([bed.style.left, bed.style.translate]).toEqual(["100%", "-100% 0"]) // ends at the right
    await user.click(screen.getByRole("button", { name: "Close" }))
  })
})
