import { describe, expect, it, vi } from "vitest"
import { passkeyLater, signInPage, signOut, whoAmI } from "./session"

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })

describe("who is signed in", () => {
  it("is the account a hosted Friday answers with", async () => {
    const me = { email: "you@gmail.com", username: "ruben", name: "Ruben" }
    expect(await whoAmI(async () => json(me))).toEqual(me)
  })
  it("is nobody on your own Friday, where /auth/me is the website's page", async () => {
    expect(await whoAmI(async () => new Response("<html>", { headers: { "content-type": "text/html" } }))).toBeNull()
  })
  it("is nobody when the server doesn't answer or refuses", async () => {
    expect(await whoAmI(async () => Promise.reject(new Error("offline")))).toBeNull()
    expect(await whoAmI(async () => json({ signin: "/signin" }, 401))).toBeNull()
  })
})

describe("Not now, on the passkey offer (H94)", () => {
  it("tells the server, so this browser isn't asked again", async () => {
    const asked: string[] = []
    await passkeyLater((async (url: string | URL | Request, init?: RequestInit) => {
      asked.push(`${init?.method} ${String(url)}`)
      return new Response("{}", { status: 200 })
    }) as typeof fetch)
    expect(asked).toEqual(["POST /auth/passkey/later"])
  })
  it("doesn't throw when the server can't be reached: the bar is already gone", async () => {
    await expect(passkeyLater((async () => Promise.reject(new Error("offline"))) as typeof fetch)).resolves.toBeUndefined()
  })
  it("comes from who is signed in", async () => {
    const me = { email: "you@gmail.com", username: "ruben", name: "Ruben", offer_passkey: true }
    expect((await whoAmI(async () => json(me)))?.offer_passkey).toBe(true)
  })
})

describe("signing out", () => {
  it("asks the server, clears every cache the page kept, then opens the sign-in page", async () => {
    const order: string[] = []
    const deleted: string[] = []
    vi.stubGlobal("caches", { keys: async () => ["friday-shell", "friday-data"], delete: async (k: string) => deleted.push(k) })
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      order.push(`${init?.method} ${String(url)}`)
      return new Response(null, { status: 200 })
    }) as unknown as typeof fetch
    await signOut(fetcher, (path) => order.push(`go ${path}`))
    expect(order).toEqual(["POST /auth/signout", "go /signin"])
    expect(deleted).toEqual(["friday-shell", "friday-data"])
    vi.unstubAllGlobals()
  })
  it("still clears and leaves when the server can't be reached", async () => {
    const went: string[] = []
    vi.stubGlobal("caches", { keys: async () => [], delete: async () => true })
    await signOut((async () => Promise.reject(new Error("offline"))) as typeof fetch, (p) => went.push(p))
    expect(went).toEqual(["/signin"])
    vi.unstubAllGlobals()
  })
})

describe("a 401 that says where to sign in", () => {
  it("names the sign-in page", () => expect(signInPage(401, { signin: "/signin" })).toBe("/signin"))
  it("is nothing for any other answer, or a page elsewhere", () => {
    expect(signInPage(403, { signin: "/signin" })).toBeNull()
    expect(signInPage(401, { message: "unknown token" })).toBeNull()
    expect(signInPage(401, { signin: "https://evil.example/" })).toBeNull()
    expect(signInPage(401, null)).toBeNull()
  })
})
