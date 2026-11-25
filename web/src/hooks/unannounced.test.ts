// 24 Nov, the new browser tests: commands kept out of the undo log (Make token, a mailbox forgotten, an AI key) aren't
// announced by the server, and the page only refreshed itself when the live stream was down: a new token didn't show
// under "Your tokens" until the page was reloaded, and no toast said it was done. Such a command (no command id)
// refreshes what it touches itself, and its words show, without Undo.
import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Toast } from "@/components/Toasts"

const stale = vi.fn()
vi.mock("@/api/events", async (original) => ({ ...(await original<typeof import("@/api/events")>()), streamLive: true, staleSoon: (...a: unknown[]) => stale(...a) }))
const { clearLanes, runCommand } = await import("./useCommand")

function answer(body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })))
}

afterEach(() => (vi.unstubAllGlobals(), clearLanes(), stale.mockClear()))

describe("a command the server doesn't announce", () => {
  it("refreshes what it touches itself, and says it's done without Undo", async () => {
    const toasts: Toast[] = []
    answer({ command_id: null, result: { token: "secret", id: 3 } })
    await runCommand(new QueryClient(), (t) => toasts.push(t), "token_add", { name: "Shortcuts" } as never, { label: () => "Token made" })
    expect(stale).toHaveBeenCalled()
    expect(toasts).toEqual([{ message: "Token made" }])
  })

  it("one the server announces is left to the stream, as before", async () => {
    answer({ command_id: 7, result: { item: {} } })
    await runCommand(new QueryClient(), () => {}, "done", { id: 2 } as never)
    expect(stale).not.toHaveBeenCalled()
  })
})
