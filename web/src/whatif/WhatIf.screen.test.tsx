// What if over Alex's sample: started from the Plan menu, it's a mode the header says you're in; what you try is kept
// beside the week rather than sent, planned with your week to say how it lands, and made real only on Keep.
import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"
import { whatIf } from "./store"

afterEach(() => whatIf.stop())

const bar = () => screen.getByRole("group", { name: "What if" })
const tryBox = () => screen.getByRole("textbox", { name: "Something to try" })

async function startWhatIf() {
  const view = await openFriday("/")
  const { user } = view
  await user.click(await screen.findByRole("button", { name: "Plan" }))
  await user.click(await screen.findByRole("button", { name: /^What if/ }))
  await screen.findByRole("group", { name: "What if" })
  return view
}

describe("What if", () => {
  it("starts from the Plan menu, with nothing tried yet and a way out", async () => {
    const { user } = await startWhatIf()
    expect(within(bar()).getByText("nothing tried yet")).toBeTruthy()
    expect(screen.getByText(/Nothing is saved. The calendar shows your week with these changes/)).toBeTruthy()
    expect(screen.getByText(/Try things as you normally would/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Leave What if" }))
    await waitFor(() => expect(screen.queryByRole("group", { name: "What if" })).toBeNull())
  })

  it("tries a to-do typed in words, says how it lands, and keeps it", async () => {
    const { user } = await startWhatIf()
    // an example fills the box
    await user.click(screen.getByRole("button", { name: "essay ~3h due thu 5pm" }))
    expect((tryBox() as HTMLInputElement).value).toBe("essay ~3h due thu 5pm")
    expect(screen.getByRole("button", { name: "Try" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Try" }))
    expect((tryBox() as HTMLInputElement).value).toBe("")
    expect(screen.getByText("Trying")).toBeTruthy()
    expect(screen.getByText("Add essay ~3h due thu 5pm")).toBeTruthy()
    expect(within(bar()).getByText("· 1 change")).toBeTruthy()
    // nothing was sent: it's tried, not made
    expect(sent.some((s) => s.name === "add")).toBe(false)
    expect(screen.getByText("How it lands")).toBeTruthy()
    await waitFor(() => expect(within(bar()).getByText(/^(Fits|Tight|Late)$/)).toBeTruthy(), { timeout: 60_000 })
    const keep = screen.getByRole("button", { name: /Keep it/ })
    await waitFor(() => expect((keep as HTMLButtonElement).disabled).toBe(false))
    await user.click(keep)
    const kept = await waitForSent("whatif_keep")
    expect(kept.body).toEqual({ changes: [{ command: "add", input: { text: "essay ~3h due thu 5pm" } }] })
    await waitFor(() => expect(screen.queryByRole("group", { name: "What if" })).toBeNull())
    const items = await friday.q<{ title: string }[]>("items")
    expect(items.some((i) => /essay/i.test(i.title))).toBe(true)
  }, 90_000)

  it("tries a rule said in words, takes a change out, and discards the rest", async () => {
    const { user } = await startWhatIf()
    await user.type(tryBox(), "No work after 10pm")
    expect(screen.getByRole("button", { name: "Try rule" })).toBeTruthy()
    await user.keyboard("{Enter}")
    expect(screen.getByText("Rule: No work after 10pm")).toBeTruthy()
    await user.type(tryBox(), "dinner with Sam fri 7–10pm")
    await user.click(screen.getByRole("button", { name: "Try" }))
    expect(within(bar()).getByText("· 2 changes")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Keep all 2" })).toBeTruthy()
    // the first taken out: the other stays
    await user.click(screen.getAllByRole("button", { name: "Take this out" })[0])
    expect(screen.queryByText("Rule: No work after 10pm")).toBeNull()
    expect(within(bar()).getByText("· 1 change")).toBeTruthy()
    await user.click(within(bar()).getByRole("button", { name: "Discard" }))
    await waitFor(() => expect(screen.queryByRole("group", { name: "What if" })).toBeNull())
    expect(sent.some((s) => s.name === "whatif_keep" || s.name === "rule_add")).toBe(false)
  })

  it("hides the changes and shows them again from the header", async () => {
    const { user } = await startWhatIf()
    await user.click(screen.getByRole("button", { name: "Hide the changes" }))
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Something to try" })).toBeNull())
    expect(bar()).toBeTruthy()
    await user.click(within(bar()).getByRole("button", { name: /nothing tried yet/ }))
    expect(await screen.findByRole("textbox", { name: "Something to try" })).toBeTruthy()
    await user.click(within(bar()).getByRole("button", { name: "Leave" }))
    await waitFor(() => expect(screen.queryByRole("group", { name: "What if" })).toBeNull())
  })
})
