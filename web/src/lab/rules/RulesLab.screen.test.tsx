// The Rules lab (/lab/rules): six prototypes of another Rules page, each on the real plan, listed and each opened.
import { cleanup, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday } from "@/test/friday"

const DIRECTIONS = [
  ["impact", "Impact"],
  ["dials", "Dials"],
  ["sentences", "Sentences"],
  ["ranking", "Priorities"],
  ["week", "Week with toggles"],
  ["teach", "Teach by example"],
] as const

describe("the Rules lab", () => {
  it("lists the six directions, each a link to its prototype", async () => {
    await openFriday("/lab/rules")
    expect(await screen.findByText("Directions")).toBeTruthy()
    for (const [slug, title] of DIRECTIONS) expect(screen.getByRole("link", { name: new RegExp(`^${title}`) }).getAttribute("href")).toBe(`#/lab/rules/${slug}`)
  })

  it("opens each prototype from its link", async () => {
    for (const [slug, title] of DIRECTIONS) {
      cleanup()
      const { user } = await openFriday("/lab/rules")
      await user.click(await screen.findByRole("link", { name: new RegExp(`^${title}`) }))
      await waitFor(() => expect(window.location.hash).toBe(`#/lab/rules/${slug}`))
      expect((await screen.findAllByText(title)).length).toBeGreaterThan(0)
    }
  }, 60_000)

  it("an address it doesn't know shows the list", async () => {
    await openFriday("/lab/rules/nowhere")
    expect(await screen.findByText("Directions")).toBeTruthy()
  })
})
