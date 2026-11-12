// What the Settings screen tests share: a stand-in for a service Friday would reach over the internet (a little HTTP
// server on this machine, which the Friday under test is pointed at by its FRIDAY_API_* variables), and answers the
// page gets instead of the server's, for what the sample can't be (a phone on Tailscale, a newer version out).
// Nothing here reaches a real service.

import { createServer, type IncomingMessage, type ServerResponse } from "node:http"
import { configure, waitFor } from "@testing-library/react"
import { beforeAll, expect } from "vitest"
import { sent } from "@/test/friday"

// A whole Friday answering on a busy machine: a second's wait for what shows is too little at times.
configure({ asyncUtilTimeout: 5000 })

// The commands the page has sent and the server hasn't answered yet (counted over setup.ts's fetch).
let unanswered = 0
beforeAll(() => {
  const inner = window.fetch
  const counted = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
    if ((init?.method ?? "GET").toUpperCase() !== "POST" || !url.includes("/api/c/")) return inner(input, init)
    unanswered++
    try {
      return await inner(input, init)
    } finally {
      unanswered--
    }
  }) as typeof fetch
  window.fetch = counted
  globalThis.fetch = counted
})

/** Waits until the server has answered every command the page sent, then asks again for what they changed, as the
 * server's live updates would (happy-dom has no stream for them). */
export async function answered(client: { invalidateQueries: () => Promise<void> }) {
  await waitFor(() => expect(unanswered).toBe(0))
  await client.invalidateQueries()
}

type Reply = { status?: number; json?: unknown; text?: string; type?: string }
type Route = (req: IncomingMessage, body: string) => Reply | undefined

/** A stand-in service on a port of its own: `route` answers each request; what was asked is kept in `asked`. */
export async function standIn(route: Route): Promise<{ url: string; asked: string[]; close: () => void }> {
  const asked: string[] = []
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    let body = ""
    req.on("data", (d: Buffer) => (body += d.toString()))
    req.on("end", () => {
      asked.push(`${req.method} ${req.url}`)
      const reply = route(req, body) ?? { status: 404, json: { error: "not here" } }
      res.writeHead(reply.status ?? 200, { "content-type": reply.type ?? (reply.text !== undefined ? "text/plain" : "application/json") })
      res.end(reply.text ?? JSON.stringify(reply.json ?? {}))
    })
  })
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", () => done()))
  const { port } = server.address() as { port: number }
  return { url: `http://127.0.0.1:${port}`, asked, close: () => server.close() }
}

type Answer = (body: unknown, url: URL) => { status?: number; json: unknown } | undefined

/** The page's fetches for `name` (a query or a command) answered here, not by the server; a command answered here is
 * still noted in `sent`. Returns the way back to the server's answers. */
export function answer(name: string, reply: Answer): () => void {
  const inner = window.fetch
  const swapped = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, window.location.href)
    const found = /^\/api\/([qc])\/([a-z_0-9]+)$/.exec(url.pathname)
    if (found && found[2] === name) {
      let body: unknown = null
      try {
        body = typeof init?.body === "string" ? JSON.parse(init.body) : null
      } catch {
        body = init?.body
      }
      const out = reply(body, url)
      if (out) {
        if (found[1] === "c") sent.push({ name, body })
        return new Response(JSON.stringify(out.json), { status: out.status ?? 200, headers: { "content-type": "application/json" } })
      }
    }
    return inner(input, init)
  }) as typeof fetch
  window.fetch = swapped
  globalThis.fetch = swapped
  return () => {
    window.fetch = inner
    globalThis.fetch = inner
  }
}

/** A command's answer as the server words one: `{command_id, result}`; one with an id, so the page says it in a toast. */
export const done = (result: unknown) => ({ json: { command_id: -1, result } })

/** A refusal as the server words one: a field and what's wrong with it. */
export const refused = (field: string, message: string) => ({ status: 400, json: { field, message } })
