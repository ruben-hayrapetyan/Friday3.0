// Each screen-test file: its own copy of Alex's sample served by a real Friday (server.ts), the page's address
// moved to it so the app's fetches reach it as they would in a browser, and every command the app sends noted, so
// a test can say what a click sent. What browsers have and happy-dom doesn't is stood in for here.

import { cleanup, configure } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, inject } from "vitest"
import { copyOf, freePort, serve, stop } from "./server"

// A real server answers, and replans after each change: waits get ten seconds, not testing-library's one (a save,
// then the list read again, often took longer while other files ran too)
configure({ asyncUtilTimeout: 10_000 })

type Sent = { name: string; body: unknown }
/** The commands the app sent, oldest first: `sent.at(-1)?.name`. */
export const sent: Sent[] = []
let server: Awaited<ReturnType<typeof serve>> | null = null
let base = ""

/** The server this file talks to: for a test that reads Friday's state directly. */
export const friday = {
  get base() {
    return base
  },
  async q<T = unknown>(name: string, params: Record<string, string> = {}): Promise<T> {
    const text = new URLSearchParams(params).toString()
    return (await (await window.fetch(`${base}/api/q/${name}${text ? `?${text}` : ""}`)).json()) as T
  },
  async c<T = unknown>(name: string, body: unknown = {}): Promise<T> {
    const answer = await window.fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
    return (await answer.json()) as T
  },
}

beforeAll(async () => {
  const port = await freePort()
  server = await serve(copyOf(inject("fridaySample")), port, 60)
  base = `http://127.0.0.1:${port}`
  const page = (window as unknown as { happyDOM: { setURL(url: string): void; setViewport(v: { width: number; height: number }): void } }).happyDOM
  page.setURL(`${base}/`)
  page.setViewport({ width: 1440, height: 900 }) // a laptop's window: the sidebar shows
  const fetchHere = window.fetch.bind(window)
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
    const command = /\/api\/c\/([a-z_0-9]+)/.exec(url)
    if (command && (init?.method ?? "GET").toUpperCase() === "POST") {
      let body: unknown = null
      try {
        body = typeof init?.body === "string" ? JSON.parse(init.body) : null
      } catch {
        body = init?.body
      }
      sent.push({ name: command[1], body })
    }
    return fetchHere(input, init)
  }) as typeof fetch
  globalThis.fetch = window.fetch
}, 90_000)

afterEach(() => {
  cleanup()
  sent.length = 0
  window.localStorage.clear()
  window.location.hash = ""
})

afterAll(async () => {
  if (server) await stop(server)
})

// What happy-dom lacks: the live updates' stream (the tests ask again instead), and a few measurements.
class QuietEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onopen: ((e: Event) => void) | null = null
  readyState = 1
  addEventListener() {}
  removeEventListener() {}
  close() {
    this.readyState = 2
  }
}
Object.assign(window, { EventSource: QuietEventSource })
Object.assign(globalThis, { EventSource: QuietEventSource })
if (!("ResizeObserver" in window)) {
  Object.assign(window, {
    ResizeObserver: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  })
}
window.scrollTo = () => {}
Element.prototype.scrollIntoView = function () {}
