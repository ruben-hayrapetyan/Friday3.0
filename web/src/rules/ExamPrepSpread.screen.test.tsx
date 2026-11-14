// The built-in rule that spreads exam prep (14 Nov), over Alex's sample: in Rules in plain words, among the rules
// people tune (not folded away), with its switch and its pencil; never the old "Spread out what you marked spread".
import { screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday, waitForSent } from "@/test/friday"

const SAID = "Exam prep is spread over the days before the exam, not crammed into one"

describe("exam prep spread over the days before the exam", () => {
  it("shows in Rules with that wording, its switch and its pencil", async () => {
    const { user } = await openFriday("/rules")
    const on = await screen.findByRole("switch", { name: `Switch off ${SAID}` })
    const row = on.closest(".fr-rule-row") as HTMLElement
    expect(row.closest("details")).toBeNull() // with the rules people tune
    expect(within(row).getByText("Built in")).toBeTruthy()
    expect(screen.queryByText(/marked spread/)).toBeNull()
    await user.click(within(row).getByRole("button", { name: "Edit rule" }))
    expect(await screen.findByText(/Editing a built-in rule/)).toBeTruthy()
    await user.click(on)
    expect((await waitForSent("rule_set")).body).toEqual({ name: "exam_prep_spread", enabled: false })
  })
})
