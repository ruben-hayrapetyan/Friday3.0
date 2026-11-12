// Opening Friday in a screen test: the whole app (App.tsx's Friday) on a page, at a route, over the real server
// setup.ts started, with a fresh cache, and a user to click and type as you would.

import { QueryClient } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Friday } from "@/App"

export { friday, sent } from "./setup"

/** Friday at `route` ("/", "/todo", "/inbox", "/settings/integrations"…), once its shell shows. */
export async function openFriday(route = "/") {
  window.location.hash = `#${route}`
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30_000 } } })
  const user = userEvent.setup()
  const view = render(<Friday client={client} />)
  await screen.findByRole("button", { name: "Settings" }, { timeout: 20_000 })
  return { ...view, client, user }
}

/** Waits for the commands the app sends: the last one named `name`. */
export async function waitForSent(name: string, timeout = 5000) {
  const { sent } = await import("./setup")
  const until = Date.now() + timeout
  while (Date.now() < until) {
    const found = [...sent].reverse().find((s) => s.name === name)
    if (found) return found
    await new Promise((r) => setTimeout(r, 50))
  }
  throw new Error(`no ${name} was sent; sent: ${sent.map((s) => s.name).join(", ") || "nothing"}`)
}
