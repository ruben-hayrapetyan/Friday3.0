import { describe, expect, it, vi } from "vitest"
import { addPasskey, canMakePasskeys, creationOptions, fromBase64url, listPasskeys, removePasskey, toBase64url } from "./passkeys"

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })

describe("base64url", () => {
  it("goes there and back for every length, with no padding or + and /", () => {
    for (const n of [0, 1, 2, 3, 4, 31, 32, 33]) {
      const bytes = Uint8Array.from({ length: n }, (_, i) => (i * 97 + 251) % 256)
      const text = toBase64url(bytes)
      expect(text).not.toMatch(/[=+/]/)
      expect(Array.from(fromBase64url(text))).toEqual(Array.from(bytes))
    }
  })
})

describe("who can make a passkey", () => {
  it("is a browser with WebAuthn", () => expect(canMakePasskeys({ PublicKeyCredential: class {}, navigator: { userAgent: "Chrome/131" } })).toBe(true))
  it("is not the Mac app's window, nor a browser without WebAuthn", () => {
    expect(canMakePasskeys({ PublicKeyCredential: class {}, navigator: { userAgent: "AppleWebKit FridayMac" } })).toBe(false)
    expect(canMakePasskeys({ navigator: { userAgent: "Chrome/131" } })).toBe(false)
  })
})

describe("the server's options for the browser", () => {
  it("turn the challenge, your id and the keys to leave out into bytes, and keep the rest", () => {
    const made = creationOptions({ challenge: "AQID", rp: { id: "x" }, user: { id: "MQ", name: "r" }, excludeCredentials: [{ id: "BAU", type: "public-key" }] })
    expect(Array.from(made.challenge as Uint8Array)).toEqual([1, 2, 3])
    expect(Array.from(made.user.id as Uint8Array)).toEqual([49])
    expect(Array.from(made.excludeCredentials![0].id as Uint8Array)).toEqual([4, 5])
    expect(made.rp).toEqual({ id: "x" })
  })
})

describe("adding, listing and removing", () => {
  it("makes the passkey with the server's options and sends back what the browser made", async () => {
    const sent: unknown[] = []
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith("/options")) return json({ flow: "f1", options: { challenge: "AQID", user: { id: "MQ", name: "r" } } })
      sent.push(JSON.parse(String(init?.body)))
      return json({ id: "k1", name: "Mac, Chrome" })
    }) as unknown as typeof fetch
    const credentials = {
      create: async () => ({
        id: "k1", rawId: new Uint8Array([9]).buffer, type: "public-key", authenticatorAttachment: "platform",
        getClientExtensionResults: () => ({}),
        response: { clientDataJSON: new Uint8Array([1]).buffer, attestationObject: new Uint8Array([2]).buffer, getTransports: () => ["internal"] },
      }),
    } as unknown as CredentialsContainer
    expect(await addPasskey(fetcher, credentials)).toBe("Mac, Chrome")
    expect(sent).toEqual([{ flow: "f1", credential: { id: "k1", rawId: "CQ", type: "public-key", authenticatorAttachment: "platform", clientExtensionResults: {},
      response: { clientDataJSON: "AQ", attestationObject: "Ag", transports: ["internal"] } } }])
  })
  it("says the server's reason when it refuses", async () => {
    const fetcher = (async () => json({ message: "That took too long; try again." }, 400)) as typeof fetch
    await expect(addPasskey(fetcher, {} as CredentialsContainer)).rejects.toThrow("too long")
  })
  it("lists nothing on your own Friday, where the address is the website's page", async () => {
    expect(await listPasskeys(async () => new Response("<html>", { headers: { "content-type": "text/html" } }))).toEqual([])
    expect(await listPasskeys(async () => json([{ id: "k1", name: "Mac, Chrome", created: 1, used: null }]))).toHaveLength(1)
  })
  it("removes one by its id", async () => {
    let body = ""
    expect(await removePasskey("k1", (async (_u: unknown, init?: RequestInit) => ((body = String(init?.body)), json({ removed: true }))) as typeof fetch)).toBe(true)
    expect(JSON.parse(body)).toEqual({ id: "k1" })
  })
})
