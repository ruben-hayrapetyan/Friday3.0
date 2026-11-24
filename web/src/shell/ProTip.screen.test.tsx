// Pro tips (#23, 24 Nov): a short line that slides in at the bottom right a few seconds after Friday opens, for five
// seconds, then out; Friday counts it, so nothing else is shown that day. A click opens the page the feature is on.
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday } from "@/test/friday"
import { friday } from "@/test/setup"
import { TIP_AFTER_MS } from "./ProTip"

type Tip = { id: string | null; text: string | null; page: string | null }
const route = () => window.location.hash.replace(/^#/, "").split("?")[0] || "/"

/** A tip the sample has, or meal events made so it has one. */
async function aTip(): Promise<Tip> {
  let tip = await friday.q<Tip>("tips")
  if (tip.id) return tip
  const day = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10)
  for (const n of [1, 2, 3]) await friday.c("add", { title: "Lunch", when: "fixed", start: `${day(n)}T12:00`, end: `${day(n)}T12:30` })
  tip = await friday.q<Tip>("tips")
  expect(tip.id, "a tip to show").toBeTruthy()
  return tip
}

describe("a pro tip", () => {
  it("slides in a few seconds after Friday opens, opens its page when clicked, and is counted for the day", async () => {
    const tip = await aTip()
    const { user } = await openFriday("/settings/appearance")
    expect(screen.queryByText(tip.text!)).toBeNull() // not at once
    const shown = await screen.findByText(tip.text!, {}, { timeout: TIP_AFTER_MS + 4000 })
    await waitFor(async () => expect((await friday.q<Tip>("tips")).id).toBeNull()) // one a day: counted
    await user.click(shown)
    await waitFor(() => expect(route()).toBe(tip.page))
    await waitFor(() => expect(screen.queryByText(tip.text!)).toBeNull())
  }, 30_000)

})
