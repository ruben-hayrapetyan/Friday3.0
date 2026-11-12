// Rules over Alex's sample: typing a rule shows how Friday read it, to correct and weigh before adding; what Friday
// can't read goes to the AI; every rule below has its switch, its strength and delete; rules that bend can ask what
// they're up against, and rules that contradict say so. Your week's paces are here too.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Rule = { name: string; sentence: string; enabled: boolean; strength: string; source: string; wins_over?: string[]; gives_way_to?: string[] }
const rules = () => friday.q<Rule[]>("rules")
const rule = async (sentence: string) => (await rules()).find((r) => r.sentence === sentence)

const box = () => screen.getByRole("textbox", { name: "New rule" })
/** The box a new rule is typed in, with Friday's reading of it. */
const newRule = () => within(box().closest('[data-tour="rule-new"]') as HTMLElement)
/** The rule's row: the switch's row, found by its sentence. */
const rowOf = (sentence: string) => screen.getByRole("switch", { name: new RegExp(`^Switch (off|on) ${sentence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }).closest(".fr-rule-row") as HTMLElement

describe("the Rules page", () => {
  it("lists every rule with how many are on and yours, and the built-in rest folded away", async () => {
    await openFriday("/rules")
    expect(await screen.findByText(/^\d+ on, 3 of them yours$/)).toBeTruthy()
    expect(screen.getByText("No work after 11pm")).toBeTruthy()
    expect(screen.getAllByText("Yours").length).toBe(3)
    expect(screen.getAllByText("Built in").length).toBeGreaterThan(3)
    expect(screen.getByText(/How Friday fills in the rest \(\d+\)/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /Try new rule designs/ }).getAttribute("href")).toContain("/lab/rules")
  })

  it("offers examples to try, and one picked fills the box with how Friday reads it", async () => {
    const { user } = await openFriday("/rules")
    await user.click(await screen.findByRole("button", { name: "Deep work in the morning" }))
    expect((box() as HTMLInputElement).value).toBe("Deep work in the morning")
    expect(await screen.findByText("Friday read this as")).toBeTruthy()
    expect(await screen.findByText("Deep work between 8am and 12pm")).toBeTruthy()
    // what, when and which days, to correct
    expect((screen.getByRole("textbox", { name: "What" }) as HTMLInputElement).value).toBe("deep work")
    expect(screen.getByRole("button", { name: "Every day" }).getAttribute("aria-pressed")).toBe("true")
  })

  it("adds a rule as read, at the strength you pick", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "No work after 10pm")
    expect(await screen.findByText("Friday read this as")).toBeTruthy()
    expect(screen.getByText(/Friday avoids those hours, unless it has to./)).toBeTruthy()
    await user.click(newRule().getByRole("button", { name: "Always" }))
    expect(await screen.findByText(/Friday avoids those hours, and never bends./)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add rule" }))
    const sent = await waitForSent("rule_add")
    expect(sent.body).toMatchObject({ text: "No work after 10pm", strength: "Always", overrides: {} })
    // the box clears, and the rule is listed with its switch
    await waitFor(() => expect((box() as HTMLInputElement).value).toBe(""))
    expect((await rule("No work after 10pm"))?.strength).toBe("Always")
  })

  it("corrects what Friday read: which days, when, and back to its reading", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "No gaming after 9pm")
    await screen.findByText("Friday read this as")
    await user.click(screen.getByRole("button", { name: "Weekdays" }))
    await user.click(await screen.findByRole("button", { name: "between" }))
    expect(await screen.findByRole("button", { name: "Use Friday’s reading" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Use Friday’s reading" }))
    await waitFor(() => expect(screen.queryByRole("button", { name: "Use Friday’s reading" })).toBeNull())
    await user.click(screen.getByRole("button", { name: "Weekends" }))
    await screen.findByRole("button", { name: "Use Friday’s reading" })
    // ↩ in the box adds it, with the correction
    await user.click(box())
    await user.keyboard("{Enter}")
    const sent = await waitForSent("rule_add")
    expect(sent.body).toMatchObject({ text: "No gaming after 9pm", overrides: { days: ["sat", "sun"] } })
  })

  it("reads a cap with its hours to change, and says what it overlaps", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "At most 6 hours a day")
    expect(await screen.findByText("At most 6 h a day")).toBeTruthy()
    expect(await screen.findByText(/Overlaps/)).toBeTruthy()
    expect(screen.getByText(/the lower one is what counts/)).toBeTruthy()
    const hours = screen.getByRole("spinbutton")
    expect((hours as HTMLInputElement).value).toBe("6")
  })

  it("warns before adding a rule that contradicts one, and can add it in that one's place", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "Keep Saturday mornings free")
    expect(await screen.findByText(/Contradicts/)).toBeTruthy()
    expect(screen.getByText(/together they leave no time for gym on Saturdays/)).toBeTruthy()
    expect(screen.getByText(/Friday would bend one of them/)).toBeTruthy()
    await user.click(newRule().getByRole("button", { name: "Always" }))
    expect(await screen.findByText(/This one is Always, so that one would give way there./)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add this, and switch that one off" }))
    expect((await waitForSent("rule_add")).body).toMatchObject({ text: "Keep Saturday mornings free", strength: "Always" })
    expect((await waitForSent("rule_set")).body).toEqual({ name: "you:gym-between-8am-and-12pm", enabled: false })
    await waitFor(async () => expect((await rule("Gym between 8am and 12pm"))?.enabled).toBe(false))
  })

  it("says how a pace for a day reads, with no strength to pick", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "Go easier on Saturdays")
    expect(await screen.findByText(/It shows under Your week./)).toBeTruthy()
    expect(screen.queryByText("Strength")).toBeNull()
  })

  it("says how a rule about events reads, and one placed close to its exam", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "Gym is optional")
    expect(await screen.findByText(/uses their time only when work would be late otherwise/)).toBeTruthy()
    await user.clear(box())
    await user.type(box(), "Exam prep as close to the exam as possible")
    expect(await screen.findByText(/unless work would be late./)).toBeTruthy()
    expect(screen.getByText("Strength")).toBeTruthy()
  })

  it("hands what Friday can't read to the AI, and adds what it ticks", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "blorp the zinger")
    expect(await screen.findByText(/Friday can’t read this one itself/)).toBeTruthy()
    const ask = screen.getByRole("button", { name: /^Ask / })
    await user.click(ask)
    const asked = await waitForSent("ask_claude")
    expect(asked.body).toEqual({ text: "blorp the zinger", purpose: "rule" })
    // whatever it answers is shown here, before anything changes
    expect(await newRule().findByText(/read this as|had no rule to suggest|couldn’t read it/, undefined, { timeout: 20_000 })).toBeTruthy()
    // the sample's stand-in AI has no rule for it: the button asks again
    expect(newRule().getByRole("button", { name: /Ask again|Add/ })).toBeTruthy()
  })

  it("asks the AI to read again a rule Friday read, and goes back to Friday's reading", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "No work after 10pm on Sundays")
    await screen.findByText(/Friday read this as/)
    await user.click(screen.getByRole("button", { name: /Not what you meant\? Ask/ }))
    await waitForSent("ask_claude")
    await user.click(await screen.findByRole("button", { name: "Back to Friday’s reading" }, { timeout: 20_000 }))
    expect(await screen.findByText(/Friday read this as/)).toBeTruthy()
  })

  it("switches a rule off and on", async () => {
    const { user } = await openFriday("/rules")
    const off = await screen.findByRole("switch", { name: "Switch off No work after 11pm" })
    await user.click(off)
    expect((await waitForSent("rule_set")).body).toEqual({ name: "you:no-work-after-11pm", enabled: false })
    await waitFor(async () => expect((await rule("No work after 11pm"))?.enabled).toBe(false))
  })

  it("shows a rule switched off as off, and switches it on", async () => {
    const { user } = await openFriday("/rules")
    const on = await screen.findByRole("switch", { name: "Switch on No work after 11pm" })
    expect(on.getAttribute("aria-checked")).toBe("false")
    await user.click(on)
    expect((await waitForSent("rule_set")).body).toEqual({ name: "you:no-work-after-11pm", enabled: true })
    await waitFor(async () => expect((await rule("No work after 11pm"))?.enabled).toBe(true))
  })

  it("changes how strongly a rule holds", async () => {
    const { user } = await openFriday("/rules")
    const row = await waitFor(() => rowOf("No work after 9pm on Fri"))
    await user.click(within(row).getByRole("button", { name: "Strongly" }))
    expect((await waitForSent("rule_set")).body).toEqual({ name: "you:no-work-after-9pm-on-fri", strength: "Strongly" })
    await waitFor(async () => expect((await rule("No work after 9pm on Fri"))?.strength).toBe("Strongly"))
    // a built-in rule bends at most strongly: no Always to pick
    expect(within(rowOf("Wind down before bed")).queryByRole("button", { name: "Always" })).toBeNull()
  })

  it("deletes a rule of yours", async () => {
    const { user } = await openFriday("/rules")
    await screen.findByText("No work after 9pm on Fri")
    await user.click(within(rowOf("No work after 9pm on Fri")).getByRole("button", { name: "Delete rule" }))
    expect((await waitForSent("rule_remove")).body).toEqual({ name: "you:no-work-after-9pm-on-fri" })
    await waitFor(async () => expect(await rule("No work after 9pm on Fri")).toBeUndefined())
  })

  it("no longer lists a rule you deleted", async () => {
    await openFriday("/rules")
    await screen.findByText("No work after 11pm")
    expect(screen.queryByText("No work after 9pm on Fri")).toBeNull()
  })

  it("asks a rule the plan bends what it's up against", async () => {
    const { user } = await openFriday("/rules")
    // the rules this plan bends, each with its question; which they are depends on the plan
    const asks = await screen.findAllByRole("button", { name: "What to?" })
    for (const what of asks) {
      const row = what.closest(".fr-rule-row") as HTMLElement
      expect(what.getAttribute("aria-expanded")).toBe("false")
      await user.click(what)
      expect(what.getAttribute("aria-expanded")).toBe("true")
      const said = await within(row).findByText(/it bends no less|This clashes with|Couldn’t find out/, undefined, { timeout: 30_000 })
      if (!said.textContent?.startsWith("This clashes with")) continue
      // two rules up against each other: the answer says which wins
      expect(within(row).getByText(/Friday remembers your answer for these two rules/)).toBeTruthy()
      const [mine] = within(row).getAllByRole("button").filter((b) => b.className.includes("btn-secondary"))
      await user.click(mine)
      expect((await waitForSent("rule_win")).body).toMatchObject({ winner: expect.any(String), loser: expect.any(String) })
      await waitFor(() => expect(within(row).queryByText(/Friday remembers your answer/)).toBeNull())
      return
    }
  })

  it("says which of two contradicting rules wins, and changes it on a click", async () => {
    await friday.c("rule_add", { text: "Keep Sunday mornings free", overrides: {}, strength: "Prefer" })
    await friday.c("rule_set", { name: "you:gym-between-8am-and-12pm", enabled: true })
    const { user } = await openFriday("/rules")
    const row = await waitFor(() => rowOf("Keep Sun 8am–12pm free"))
    expect(within(row).getByText(/Which should win\?/)).toBeTruthy()
    await user.click(within(row).getByRole("button", { name: "Keep Sun 8am–12pm free" }))
    const won = await waitForSent("rule_win")
    expect(won.body).toMatchObject({ winner: expect.stringContaining("sun"), loser: "you:gym-between-8am-and-12pm" })
    await waitFor(async () => expect((await rule("Keep Sun 8am–12pm free"))?.wins_over?.length).toBeGreaterThan(0))
  })

  it("shows the winner on both rules, and swaps it from either", async () => {
    const { user } = await openFriday("/rules")
    const wins = await screen.findByRole("button", { name: /Wins over “Gym between 8am and 12pm”/ })
    expect(screen.getByRole("button", { name: /Gives way to “Keep Sun 8am–12pm free”/ })).toBeTruthy()
    await user.click(wins)
    expect((await waitForSent("rule_win")).body).toMatchObject({ winner: "you:gym-between-8am-and-12pm" })
    await waitFor(async () => expect((await rule("Gym between 8am and 12pm"))?.wins_over?.length).toBeGreaterThan(0))
  })

  it("steps a day of your week through the paces", async () => {
    const { user } = await openFriday("/rules")
    const sat = await screen.findByRole("button", { name: /^Sat/ })
    expect(sat.getAttribute("title")).toMatch(/every week/)
    const before = sat.textContent
    await user.click(sat)
    const sent = await waitForSent("settings_set")
    expect(sent.body).toMatchObject({ key: "pace", value: { weekly: { sat: expect.any(String) } } })
    const pace = (sent.body as { value: { weekly: { sat: string } } }).value.weekly.sat
    expect(before).not.toContain(pace)
    await waitFor(async () => expect(((await friday.q("settings")) as { pace: { weekly: Record<string, string> } }).pace.weekly.sat).toBe(pace))
  })

  it("shows a day's pace set for every week", async () => {
    await openFriday("/rules")
    const sat = await screen.findByRole("button", { name: /^Sat/ })
    expect(sat.textContent).toBe("SatEasy")
  })
})
