// What the Rules page says, over Alex's sample (14 Nov): no built-in rules for work "marked" spread or clustered, and
// spreading said as a rule for the work it names; exam focus is a rule here like any other.
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Rule = { name: string; sentence: string; type: string }

describe("spreading, said as a rule", () => {
  it("lists no built-in rule for marked work", async () => {
    await openFriday("/rules")
    await screen.findByText("Deadlines come first")
    expect(screen.queryByText("Spread out what you marked spread")).toBeNull()
    expect(screen.queryByText("Keep clustered work on few days")).toBeNull()
    expect((await friday.q<Rule[]>("rules")).some((r) => r.name === "spread" || r.name === "cluster")).toBe(false)
  })

  it("reads spreading the work you name, and adds it", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "spread my essays over several days")
    expect(await screen.findByText("Spread essays over several days")).toBeTruthy()
    expect(screen.getByText(/a share a day/)).toBeTruthy()
    expect((screen.getByRole("textbox", { name: "What" }) as HTMLInputElement).value).toBe("essays")
    expect(screen.queryByText("Days")).toBeNull() // each one's own days: not which weekdays
    await user.click(screen.getByRole("button", { name: "Add rule" }))
    expect((await waitForSent("rule_add")).body).toMatchObject({ text: "spread my essays over several days" })
    await waitFor(async () => expect((await friday.q<Rule[]>("rules")).find((r) => r.sentence === "Spread essays over several days")?.type).toBe("spread"))
  })

  it("reads keeping work together", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "keep problem sets on few days")
    expect(await screen.findByText("Keep problem sets on as few days as possible")).toBeTruthy()
  })
})

describe("exam focus, a rule", () => {
  it("reads from your words with its days to change, and no strength to pick", async () => {
    const { user } = await openFriday("/rules")
    await user.type(await screen.findByRole("textbox", { name: "New rule" }), "focus on exams 5 days before")
    expect(await screen.findByText("Focus on an exam's course 5 days before it")).toBeTruthy()
    expect(((await screen.findByRole("spinbutton", { name: "Days before" })) as HTMLInputElement).value).toBe("5")
    expect(screen.queryByText("Strength")).toBeNull()
    await user.click(screen.getByRole("button", { name: "Add rule" }))
    await waitFor(async () => expect((await friday.q<Rule[]>("rules")).find((r) => r.type === "exam_focus")?.sentence).toBe("Focus on an exam's course 5 days before it"))
  })

  it("is listed in Rules with its switch, and the pencil opens its days", async () => {
    const { user } = await openFriday("/rules")
    const off = await screen.findByRole("switch", { name: "Switch off Focus on an exam's course 5 days before it" })
    const row = off.closest(".fr-rule-row") as HTMLElement
    await user.click(within(row).getByRole("button", { name: "Edit rule" }))
    expect(((await screen.findByRole("spinbutton", { name: "Days before" })) as HTMLInputElement).value).toBe("5")
  })
})
