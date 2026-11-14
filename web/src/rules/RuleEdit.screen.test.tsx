// Editing a rule where it stands (14 Nov), over Alex's sample: the pencil opens a rule in the box with your words and
// Friday's reading; Save changes it in place (its name, its place, how often it's kept), shown at once. Another kind of
// rule says before you save that it starts over; a built-in rule's number changes, not its words; Undo puts it back.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Rule = { name: string; sentence: string; strength: string; source: string; kept: string; words?: string | null; number?: { value: number } | null }
const rules = () => friday.q<Rule[]>("rules")
const named = async (name: string) => (await rules()).find((r) => r.name === name)
const editBox = () => within(document.querySelector('[data-tour="rule-new"][data-editing]') as HTMLElement)
const rowOf = (sentence: string) => screen.getByRole("switch", { name: new RegExp(`^Switch (off|on) ${sentence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }).closest(".fr-rule-row") as HTMLElement

describe("editing a rule", () => {
  it("opens your rule in the box with your words and Friday's reading, and Cancel leaves it", async () => {
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf("No work after 11pm"))).getByRole("button", { name: "Edit rule" }))
    const words = (await screen.findByRole("textbox", { name: "Rule" })) as HTMLInputElement
    expect(words.value.toLowerCase()).toContain("11")
    expect(await editBox().findByText("Friday read this as")).toBeTruthy()
    expect(editBox().getByText(/Editing/)).toBeTruthy()
    expect(editBox().getByRole("button", { name: "Every day" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(editBox().getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Rule" })).toBeNull())
    expect(screen.getByRole("textbox", { name: "New rule" })).toBeTruthy()
  })

  it("saves new words in place: the same rule, where it was, shown at once", async () => {
    const before = await rules()
    const at = before.findIndex((r) => r.sentence === "No work after 11pm")
    const { name } = before[at]
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf("No work after 11pm"))).getByRole("button", { name: "Edit rule" }))
    const words = await screen.findByRole("textbox", { name: "Rule" })
    await user.clear(words)
    await user.type(words, "no work after 10:30pm")
    expect(await editBox().findByText("No work after 10:30pm")).toBeTruthy()
    expect(editBox().queryByText(/starts over/)).toBeNull()
    await user.click(editBox().getByRole("button", { name: "Save" }))
    // the row says it before the list is read again, and the box is a new rule's again
    expect(await screen.findByRole("switch", { name: "Switch off No work after 10:30pm" })).toBeTruthy()
    expect((await waitForSent("rule_edit")).body).toMatchObject({ name, text: "no work after 10:30pm" })
    await waitFor(async () => expect((await named(name))?.sentence).toBe("No work after 10:30pm"))
    const after = await rules()
    expect(after.map((r) => r.name)).toEqual(before.map((r) => r.name)) // same name, same place
    expect(after[at].kept).toBe(before[at].kept) // and how often it's kept, counted on
    expect(screen.getByRole("textbox", { name: "New rule" })).toBeTruthy()
  })

  it("saves a corrected reading and a strength, keeping the words", async () => {
    const { name, words } = (await rules()).find((r) => r.sentence === "No work after 10:30pm") as Rule
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf("No work after 10:30pm"))).getByRole("button", { name: "Edit rule" }))
    await editBox().findByText("Friday read this as")
    await user.click(editBox().getByRole("button", { name: "Weekdays" }))
    await user.click(editBox().getByRole("button", { name: "Strongly" }))
    expect(await editBox().findByText("No work after 10:30pm on weekdays")).toBeTruthy()
    await user.click(editBox().getByRole("button", { name: "Save" }))
    const sent = await waitForSent("rule_edit")
    expect(sent.body).toMatchObject({ name, text: words, strength: "Strongly", overrides: { days: ["mon", "tue", "wed", "thu", "fri"] } })
    await waitFor(async () => expect(await named(name)).toMatchObject({ sentence: "No work after 10:30pm on weekdays", strength: "Strongly" }))
  })

  it("says before saving that another kind of rule starts over, and takes the old one's place", async () => {
    const before = await rules()
    const at = before.findIndex((r) => r.sentence === "Gym between 8am and 12pm")
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf("Gym between 8am and 12pm"))).getByRole("button", { name: "Edit rule" }))
    const words = await screen.findByRole("textbox", { name: "Rule" })
    await user.clear(words)
    await user.type(words, "lunch before 1pm")
    expect(await editBox().findByText(/another kind of rule than “Gym between 8am and 12pm”.*how often it’s kept starts over/)).toBeTruthy()
    await user.click(editBox().getByRole("button", { name: "Save" }))
    expect((await screen.findAllByText(/Replaced with a new rule: Lunch before 1pm/)).length).toBeGreaterThan(0)
    await waitFor(async () => expect((await rules())[at].sentence).toBe("Lunch before 1pm"))
    const after = await rules()
    expect(after.length).toBe(before.length)
    expect(after[at].name).not.toBe(before[at].name)
  })

  it("puts the old rule back on Undo", async () => {
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf("Lunch before 1pm"))).getByRole("button", { name: "Edit rule" }))
    const words = await screen.findByRole("textbox", { name: "Rule" })
    await user.clear(words)
    await user.type(words, "lunch before 2pm")
    await editBox().findByText("Lunch before 2pm")
    await user.click(editBox().getByRole("button", { name: "Save" }))
    await user.click(await screen.findByRole("button", { name: "Undo" }))
    await waitFor(async () => expect((await rules()).some((r) => r.sentence === "Lunch before 1pm")).toBe(true))
    expect((await rules()).some((r) => r.sentence === "Lunch before 2pm")).toBe(false)
  })

  it("changes a built-in rule's number and strength, not its words", async () => {
    const deep = (await named("deep_run")) as Rule
    const { user } = await openFriday("/rules")
    await user.click(within(await waitFor(() => rowOf(deep.sentence))).getByRole("button", { name: "Edit rule" }))
    expect(screen.queryByRole("textbox", { name: "Rule" })).toBeNull() // its words stay
    const hours = editBox().getByRole("spinbutton", { name: "Hours" }) as HTMLInputElement
    expect(Number(hours.value)).toBe(deep.number?.value)
    await user.clear(hours)
    await user.type(hours, "2")
    expect(editBox().getByText("No more than 2 h of focused work in a row")).toBeTruthy() // as you type
    expect(editBox().queryByRole("button", { name: "Always" })).toBeNull()
    await user.click(editBox().getByRole("button", { name: "Strongly" }))
    await user.click(editBox().getByRole("button", { name: "Save" }))
    expect(await screen.findByRole("switch", { name: "Switch off No more than 2 h of focused work in a row" })).toBeTruthy()
    expect((await waitForSent("rule_edit")).body).toEqual({ name: "deep_run", number: 2, strength: "Strongly" })
    await waitFor(async () => expect(await named("deep_run")).toMatchObject({ sentence: "No more than 2 h of focused work in a row", strength: "Strongly" }))
  })

  it("won't save a built-in number out of its range", async () => {
    const { user } = await openFriday("/rules")
    const load = (await named("daily_load")) as Rule
    await user.click(within(await waitFor(() => rowOf(load.sentence))).getByRole("button", { name: "Edit rule" }))
    const hours = editBox().getByRole("spinbutton", { name: "Hours" })
    await user.clear(hours)
    await user.type(hours, "40")
    expect(editBox().getByText(/from 1 to 16/)).toBeTruthy()
    expect(editBox().getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true)
  })

  it("opens a rule named in the address (?edit=)", async () => {
    await openFriday("/rules?edit=finish_early")
    expect(await screen.findByRole("spinbutton", { name: "Days" })).toBeTruthy()
    expect(editBox().getByText("Finish work a day before it’s due")).toBeTruthy()
  })
})
