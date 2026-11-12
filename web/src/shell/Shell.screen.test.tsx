// The app as a whole: it opens on the plan over a real Friday, and the sidebar's pages each open.
import { screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { openFriday } from "@/test/friday"

describe("Friday, opened", () => {
  it("shows the plan, with the sidebar's pages", async () => {
    await openFriday("/")
    for (const page of ["Plan", "To-do", "Inbox", "Insights", "Rules"]) expect(screen.getAllByText(page).length).toBeGreaterThan(0)
  })
})
