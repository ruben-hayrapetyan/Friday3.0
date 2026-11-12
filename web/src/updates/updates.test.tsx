// The updater on the page (HOSTED.md H118–H124, H144–H147). Glass box: what it says (headline, when it last looked,
// a download's progress with its seconds) and what it tells the Mac app once an update is unpacked. Black box: a
// version's notes drawn as the popup and "what's new" show them.
import { renderToStaticMarkup } from "react-dom/server"
import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Toast } from "@/components/Toasts"
import { Notes } from "./UpdateDialogs"
import { headline, lookedAgo, macMessage, progressLine, runUpdateAct, type UpdateStatus } from "./updates"

const version = (v: string) => ({ version: v, released: "2026-11-07", summary: `About ${v}.`, new: [`New in ${v}`], changed: [], fixed: [] })
const status = (over: Partial<UpdateStatus>): UpdateStatus => ({ checks: true, have: "0.1.0", state: "idle", progress: 0, versions: [], popup: false, whats_new: [], restart: "now", ...over }) as UpdateStatus

describe("what Settings → Updates and the popup say", () => {
  it("says whether a newer Friday is out, or that this build doesn't look", () => {
    expect(headline(status({}))).toBe("Friday is up to date")
    expect(headline(status({ versions: [version("0.3.0"), version("0.2.0")] }))).toBe("Friday 0.3.0 is out")
    expect(headline(status({ state: "checking" }))).toBe("Looking for a new version…")
    expect(headline(status({ state: "downloading", versions: [version("0.3.0")] }))).toBe("Downloading Friday 0.3.0")
    expect(headline(status({ checks: false }))).toBe("This Friday doesn't look for updates")
  })

  it("says when it last looked as people say it", () => {
    const now = new Date("2026-11-07T12:00:00")
    expect(lookedAgo(null, now)).toBe("Hasn't looked yet")
    expect(lookedAgo("2026-11-07T11:59:40", now)).toBe("Looked just now")
    expect(lookedAgo("2026-11-07T11:55", now)).toBe("Looked 5 minutes ago")
    expect(lookedAgo("2026-11-07T09:00", now)).toBe("Looked 3 hours ago")
    expect(lookedAgo("2026-11-06T12:00", now)).toBe("Looked yesterday")
    expect(lookedAgo("2026-10-03T12:00", now)).toBe("Looked on 3 October")
  })

  it("shows a download's progress with its seconds counting up", () => {
    expect(progressLine(0.426, 12.7)).toBe("43% · 12 s")
  })
})

describe("what the Mac app is told once an update is unpacked", () => {
  it("swap it in now, or when you quit, as Settings says (H146); nothing before it's ready", () => {
    const ready = status({ state: "ready", staged: "/Users/x/Library/Caches/Friday/updates/0.3.0/Friday.app" })
    expect(macMessage(ready)).toEqual({ update: "install", app: ready.staged })
    expect(macMessage({ ...ready, restart: "quit" })).toEqual({ update: "atQuit", app: ready.staged })
    expect(macMessage(status({ state: "downloading" }))).toBeNull()
  })
})

describe("a version's notes", () => {
  it("a sentence, then only the sections that have lines (H143)", () => {
    const page = renderToStaticMarkup(<Notes version={{ ...version("0.3.0"), fixed: ["A fix"] }} titled />)
    expect(page).toContain("Friday 0.3.0")
    expect(page).toContain("About 0.3.0.")
    expect(page).toContain("New in 0.3.0")
    expect(page).toContain("A fix")
    expect(page).not.toContain("Changed")
  })

  it("no title when it's the only version shown", () => {
    expect(renderToStaticMarkup(<Notes version={version("0.3.0")} titled={false} />)).not.toContain("Friday 0.3.0")
  })
})

describe("the updater's commands", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("says a refusal, rather than doing nothing you can see", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ field: "updates", message: "Friday isn't in Applications, so it can't be replaced" }), { status: 422 })))
    const client = new QueryClient()
    const toasts: Toast[] = []
    expect(await runUpdateAct(client, (t) => toasts.push(t), "update_start")).toBeUndefined()
    expect(toasts).toEqual([expect.objectContaining({ tone: "error", message: expect.stringContaining("can't be replaced") })])
  })

  it("shows the state it answers with at once", async () => {
    const now = status({ state: "downloading", versions: [version("0.3.0")] })
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ command_id: null, result: now }), { status: 200 })))
    const client = new QueryClient()
    expect(await runUpdateAct(client, () => {}, "update_start")).toEqual(now)
    expect(client.getQueryData(["updates"])).toEqual(now)
  })
})
