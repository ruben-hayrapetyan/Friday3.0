// Settings → Tokens, Phone and Updates, the update popup and what's new, and Friday's terms before anything else.
// Tokens are the server's own. The phone needs this Mac on Tailscale, and the Friday under test never answers there:
// its answers are given here, and so is a newer Friday to update to, since one run from its code never looks; the
// terms, accepted in the sample, are asked for again here.

import { QueryClient } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Friday } from "@/App"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"
import { answer, done, refused } from "./screen.test.helpers"

const undo: (() => void)[] = []
afterEach(() => {
  while (undo.length) undo.pop()!()
  vi.restoreAllMocks()
})

type Token = { name: string; scope: string; created: string; last_used: string | null }
const tokens = () => friday.q<Token[]>("tokens")

describe("Tokens", () => {
  it("says none can get in yet, and makes a token shown once to copy", async () => {
    const { user } = await openFriday("/settings/tokens")
    expect(await screen.findByText("No tokens. Nothing outside this app can get in.")).toBeTruthy()
    const make = screen.getByRole("button", { name: "Make token" }) as HTMLButtonElement
    expect(make.disabled).toBe(true)
    await user.type(screen.getByRole("textbox", { name: "Token name" }), "claude")
    await user.click(within(screen.getByRole("group", { name: "What it may do" })).getByRole("button", { name: "Read and change" }))
    await user.click(make)
    expect((await waitForSent("token_add")).body).toEqual({ name: "claude", scope: "read-write" })
    const shown = await screen.findByText("Copy it now; it isn’t shown again.")
    const code = shown.closest(".fr-well")!.querySelector("code")!.textContent!
    expect(code.length).toBeGreaterThan(20)
    await user.click(screen.getByRole("button", { name: "Copy" }))
    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy()
    expect(await navigator.clipboard.readText()).toBe(code)
    expect(await screen.findByText("claude")).toBeTruthy()
    expect(screen.getByText(/^Can read and make changes · made .* · never used$/)).toBeTruthy()
    expect((await tokens()).map((t) => [t.name, t.scope])).toEqual([["claude", "read-write"]])
  })

  it("won't make two tokens of one name", async () => {
    const { user } = await openFriday("/settings/tokens")
    await screen.findByText("claude")
    await user.type(screen.getByRole("textbox", { name: "Token name" }), "claude")
    expect(screen.getByText("There's already a token called claude.")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Make token" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("deletes a token after asking, and all of them at once", async () => {
    await friday.c("token_add", { name: "script", scope: "read" })
    await friday.c("token_add", { name: "shortcut", scope: "read" })
    const { user } = await openFriday("/settings/tokens")
    expect(await screen.findByText("3 in use")).toBeTruthy()
    expect(screen.getAllByText(/^Can only read · /)).toHaveLength(2)
    await user.click(screen.getByRole("button", { name: "Delete script" }))
    expect(screen.getByText("Delete script?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Keep" }))
    expect(screen.queryByText("Delete script?")).toBeNull()
    await user.click(screen.getByRole("button", { name: "Delete script" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect((await waitForSent("token_remove")).body).toEqual({ name: "script" })
    await waitFor(async () => expect((await tokens()).map((t) => t.name).sort()).toEqual(["claude", "shortcut"]))
    await screen.findByText("2 in use") // the list read again, so Delete all counts what's left
    await user.click(await screen.findByRole("button", { name: "Delete all" }))
    expect(screen.getByText("Delete all 2?")).toBeTruthy()
    sent.length = 0
    await user.click(screen.getByRole("button", { name: "Delete" }))
    await waitFor(() => expect(sent.filter((s) => s.name === "token_remove").map((s) => s.body)).toEqual([{ name: "claude" }, { name: "shortcut" }]))
    await waitFor(async () => expect(await tokens()).toEqual([]))
  })
})

describe("Phone", () => {
  const off = { on: false, address: "100.64.0.1", name: "mac.tail0000.ts.net", phones: [] }
  const phone = { id: 1, name: "Alex's iPhone", paired: "2026-11-01T09:00", last_used: "2026-11-10T21:00" }
  const fresh = { id: 2, name: "iPad", paired: "2026-11-09T09:00", last_used: null }

  it("is off until you switch it on, and then answers on the tailnet with a code to pair a phone", async () => {
    let state: Record<string, unknown> = off
    undo.push(answer("phone_status", () => ({ json: state })))
    undo.push(answer("phone_set", (body) => ((state = { ...off, on: (body as { on: boolean }).on }), done({ message: "Friday answers on your tailnet" }))))
    undo.push(answer("phone_pair", () => done({ svg: '<svg viewBox="0 0 10 10"><rect width="10" height="10"/></svg>', minutes: 10, url: "https://mac.tail0000.ts.net/pair?c=1" })))
    const { user, client } = await openFriday("/settings/phone")
    expect(await screen.findByText("Off: Friday answers on this Mac alone.")).toBeTruthy()
    expect(screen.getByText("No phone yet.")).toBeTruthy()
    await user.click(screen.getByRole("switch", { name: "Use Friday on my phone" }))
    expect((await waitForSent("phone_set")).body).toEqual({ on: true })
    await screen.findByText("Friday answers on your tailnet")
    await client.invalidateQueries({ queryKey: ["phone_status"] })
    expect(await screen.findByText("On at mac.tail0000.ts.net. Your Mac must be awake for your phone to reach it.")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Pair a phone" }))
    await waitForSent("phone_pair")
    const code = await screen.findByRole("img", { name: "Pairing code to scan" })
    expect(code.innerHTML).toContain('<svg width="180" height="180" viewBox="0 0 10 10">')
    expect(screen.getByText(/Works once, for 10 minutes/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Hide the code" }))
    expect(screen.queryByRole("img", { name: "Pairing code to scan" })).toBeNull()
    expect(screen.getByRole("button", { name: "Pair a phone" })).toBeTruthy()
  })

  it("says when this Mac isn't on Tailscale", async () => {
    undo.push(answer("phone_status", () => ({ json: { on: true, address: null, name: null, phones: [] } })))
    await openFriday("/settings/phone")
    expect(await screen.findByText(/^This Mac isn't on Tailscale. Open Tailscale and sign in/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Pair a phone" })).toBeNull()
  })

  it("lists the paired phones, each to remove", async () => {
    undo.push(answer("phone_status", () => ({ json: { ...off, phones: [phone, fresh] } })))
    undo.push(answer("phone_forget", () => done({ message: "Alex's iPhone removed" })))
    const { user } = await openFriday("/settings/phone")
    expect(await screen.findByText("Alex's iPhone")).toBeTruthy()
    expect(screen.getByText(/^Paired .* · last opened /)).toBeTruthy()
    expect(screen.getByText(/^Paired .* · not opened yet$/)).toBeTruthy()
    await user.click(screen.getAllByRole("button", { name: "Remove" })[0])
    expect((await waitForSent("phone_forget")).body).toEqual({ id: 1 })
    expect(await screen.findByText("Alex's iPhone removed")).toBeTruthy()
  })
})

type Status = Record<string, unknown>
const version = (v: string, notes: Partial<Record<"new" | "changed" | "fixed", string[]>> = {}) => ({ version: v, released: "2026-11-10", summary: `Friday ${v} plans around your shifts.`, new: [], changed: [], fixed: [], ...notes })
/** Up to date, looked 5 minutes ago by the page's clock: read when a test runs, after setup has set that clock. */
const idle = (): Status => ({ checks: true, have: "0.3.3", last_checked: new Date(Date.now() - 5 * 60_000).toISOString(), state: "idle", progress: 0, message: null, versions: [], popup: false, whats_new: [], restart: "now", staged: null })

describe("Updates", () => {
  it("says this copy doesn't look for updates, and when an update goes in", async () => {
    const { user } = await openFriday("/settings/updates")
    expect(await screen.findByText("This Friday doesn't look for updates")).toBeTruthy()
    expect(screen.getByText(/This copy doesn't check for updates; Friday Test and copies run from code never do/)).toBeTruthy()
    expect(screen.getByText("You have a build from here")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Check now" })).toBeNull()
    const restart = screen.getByRole("group", { name: "When an update goes in" })
    expect(within(restart).getByRole("button", { name: "Right away" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(within(restart).getByRole("button", { name: "When I quit Friday" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "updates", value: { restart: "quit" } })
    await waitFor(async () => expect((await friday.q<{ updates: { restart: string } }>("settings")).updates.restart).toBe("quit"))
  })

  it("checks now, saying when it last looked, and that it's up to date", async () => {
    let status = idle()
    undo.push(answer("update_status", () => ({ json: status })))
    undo.push(answer("update_check", () => ((status = { ...idle(), state: "checking" }), { json: { command_id: null, result: status } })))
    const { user } = await openFriday("/settings/updates")
    expect(await screen.findByText("Friday is up to date")).toBeTruthy()
    expect(screen.getByText("You have 0.3.3 · Looked 5 minutes ago")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Check now" }))
    await waitForSent("update_check")
    expect(await screen.findByText("Looking for a new version…")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Check now" }) as HTMLButtonElement).disabled).toBe(true)
    status = { ...idle(), message: "Couldn't reach the update feed: try again later" }
    expect(await screen.findByText("Couldn't reach the update feed: try again later", {}, { timeout: 4000 })).toBeTruthy()
  })

  it("shows a newer version's notes, and Later puts it off", async () => {
    const ready = { ...idle(), versions: [version("0.4.0", { new: ["Shifts from When I Work"], fixed: ["Sync now after waking"] }), version("0.3.4")] }
    undo.push(answer("update_status", () => ({ json: ready })))
    undo.push(answer("update_later", () => ({ json: { command_id: null, result: ready } })))
    const { user } = await openFriday("/settings/updates")
    expect(await screen.findByText("Friday 0.4.0 is out")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "See what's new" }))
    const popup = await screen.findByRole("dialog")
    expect(within(popup).getByText("Friday 0.4.0 is ready")).toBeTruthy()
    expect(within(popup).getByText("You have 0.3.3")).toBeTruthy()
    expect(within(popup).getByText("Shifts from When I Work")).toBeTruthy()
    expect(within(popup).getByText("Fixed")).toBeTruthy()
    expect(within(popup).queryByText("Changed")).toBeNull() // a heading only when it has lines
    expect(within(popup).getByText("Friday 0.3.4")).toBeTruthy()
    await user.click(within(popup).getByRole("button", { name: "Later" }))
    await waitForSent("update_later")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("updates: the download's progress, Stop, and then going in when you quit", async () => {
    const ready = { ...idle(), popup: true, restart: "quit", versions: [version("0.4.0")] }
    let status: Status = ready
    undo.push(answer("update_status", () => ({ json: status })))
    undo.push(answer("update_start", () => ((status = { ...ready, state: "downloading", progress: 0.42 }), { json: { command_id: null, result: status } })))
    undo.push(answer("update_stop", () => ((status = { ...ready, message: "Stopped. Nothing was changed." }), { json: { command_id: null, result: status } })))
    const { user } = await openFriday("/")
    // the popup at launch
    const popup = await screen.findByRole("dialog")
    expect(within(popup).getByText("Friday 0.4.0 is ready")).toBeTruthy()
    await user.click(within(popup).getByRole("button", { name: "Update" }))
    await waitForSent("update_start")
    expect(await within(popup).findByText("Downloading Friday 0.4.0")).toBeTruthy()
    expect(within(popup).getByText(/^42% · \d+ s$/)).toBeTruthy()
    expect(within(popup).getByText("You can close this and keep working; Friday carries on.")).toBeTruthy()
    await user.click(within(popup).getByRole("button", { name: "Stop" }))
    await waitForSent("update_stop")
    expect(await screen.findByText("Stopped. Nothing was changed.")).toBeTruthy()
    status = { ...ready, state: "ready", staged: "/tmp/Friday.app" }
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Update" }))
    status = { ...ready, state: "ready", staged: "/tmp/Friday.app" }
    expect(await screen.findByText("It goes in when you quit Friday, and opens the next time you do.", {}, { timeout: 4000 })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "OK" }))
    expect(screen.queryByText("It goes in when you quit Friday, and opens the next time you do.")).toBeNull()
  })

  it("tells the Mac app to swap a ready update in", async () => {
    const post = vi.fn()
    Object.assign(window, { webkit: { messageHandlers: { friday: { postMessage: post } } } })
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 FridayMac/1.0")
    undo.push(() => delete (window as { webkit?: unknown }).webkit)
    undo.push(answer("update_status", () => ({ json: { ...idle(), state: "ready", staged: "/Users/alex/Library/Caches/Friday/Friday.app", versions: [version("0.4.0")] } })))
    await openFriday("/settings/updates")
    await waitFor(() => expect(post).toHaveBeenCalledWith({ update: "install", app: "/Users/alex/Library/Caches/Friday/Friday.app" }))
    expect(await screen.findByText("Friday is restarting into it…")).toBeTruthy()
  })

  it("says what changed in the version that just opened, once", async () => {
    let status: Status = { ...idle(), whats_new: [version("0.3.3", { changed: ["Settings open where you left them"] })] }
    undo.push(answer("update_status", () => ({ json: status })))
    undo.push(answer("whats_new_seen", () => ((status = idle()), { json: { command_id: null, result: idle() } })))
    const { user } = await openFriday("/")
    const popup = await screen.findByRole("dialog")
    expect(within(popup).getByText("What's new in Friday 0.3.3")).toBeTruthy()
    expect(within(popup).getByText("Settings open where you left them")).toBeTruthy()
    await user.click(within(popup).getByRole("button", { name: "Got it" }))
    await waitForSent("whats_new_seen")
    await waitFor(() => expect(screen.queryByText("What's new in Friday 0.3.3")).toBeNull())
  })
})

describe("Friday's terms, before anything else", () => {
  type Terms = { version: string; text: string; changes: string[]; accepted: string | null; needed: boolean }

  /** Friday opened before its shell: the terms page waits for an answer. */
  async function openAtTerms() {
    window.location.hash = "#/"
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const user = userEvent.setup()
    render(<Friday client={client} />)
    return { user, client, main: await screen.findByRole("main", { name: /Friday's terms/ }, { timeout: 20_000 }) }
  }

  it("asks again when the terms changed, says what changed, and lets you in once you accept", async () => {
    const real = await friday.q<Terms>("terms")
    let terms: Terms = { ...real, accepted: "2026-01-01", changes: ["Plugins are yours to answer for"], needed: true }
    undo.push(answer("terms", () => ({ json: terms })))
    const { user, main } = await openAtTerms()
    expect(within(main).getByText("Friday's terms have changed. Read what's new and accept them to keep using Friday.")).toBeTruthy()
    expect(within(within(main).getByRole("region", { name: "What changed" })).getByText("Plugins are yours to answer for")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Settings" })).toBeNull()
    terms = { ...real, needed: false }
    await user.click(within(main).getByRole("button", { name: "Accept" }))
    expect((await waitForSent("terms_accept")).body).toEqual({ version: real.version })
    expect(await screen.findByRole("button", { name: "Settings" }, { timeout: 20_000 })).toBeTruthy()
  })

  it("reads them again when they changed while you read", async () => {
    const real = await friday.q<Terms>("terms")
    const old = { ...real, version: "2026-01-01", accepted: null, needed: true }
    let asked = 0
    undo.push(answer("terms", () => (asked++, { json: old })))
    const { user, main } = await openAtTerms()
    expect(within(main).getByText("Before you start, read Friday's terms and accept them to use Friday.")).toBeTruthy()
    await user.click(within(main).getByRole("button", { name: "Accept" }))
    expect((await waitForSent("terms_accept")).body).toEqual({ version: "2026-01-01" })
    expect(await screen.findByText("These terms changed while you were reading them: read the new ones first")).toBeTruthy()
    await waitFor(() => expect(asked).toBeGreaterThan(1))
    expect(((await screen.findByRole("button", { name: "Accept" })) as HTMLButtonElement).disabled).toBe(false)
  })

  it("Quit closes the tab, or says it can be closed", async () => {
    const real = await friday.q<Terms>("terms")
    undo.push(answer("terms", () => ({ json: { ...real, accepted: null, needed: true } })))
    const close = vi.spyOn(window, "close").mockImplementation(() => {})
    const { user, main } = await openAtTerms()
    expect(within(main).getByText("Your data stays on your computer either way.")).toBeTruthy()
    await user.click(within(main).getByRole("button", { name: "Quit" }))
    expect(close).toHaveBeenCalled()
    expect(within(main).getByText("You can close this tab now. Your data stays on your computer.")).toBeTruthy()
  })

  it("in the Mac app, Quit asks the app to quit", async () => {
    const real = await friday.q<Terms>("terms")
    undo.push(answer("terms", () => ({ json: { ...real, accepted: null, needed: true } })))
    const post = vi.fn()
    Object.assign(window, { webkit: { messageHandlers: { friday: { postMessage: post } } } })
    undo.push(() => delete (window as { webkit?: unknown }).webkit)
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 FridayMac/1.0")
    const { user, main } = await openAtTerms()
    await user.click(within(main).getByRole("button", { name: "Quit" }))
    expect(post).toHaveBeenCalledWith({ quit: true })
    expect(within(main).getByText("Your data stays on your computer either way.")).toBeTruthy()
  })
})

describe("refusals", () => {
  it("says the server's words when a token can't be made", async () => {
    undo.push(answer("token_add", () => refused("name", "name: a token's name is letters, digits and dashes")))
    const { user } = await openFriday("/settings/tokens")
    await user.type(await screen.findByRole("textbox", { name: "Token name" }), "my token")
    await user.click(screen.getByRole("button", { name: "Make token" }))
    expect(await screen.findByText("A token's name is letters, digits and dashes")).toBeTruthy()
    expect(screen.queryByText("Copy it now; it isn’t shown again.")).toBeNull()
  })
})
