// Tokens (tests/features.toml: tokens), Settings → Tokens: a token made by name and scope is shown once and listed with
// what it may do; it lets a request in as a bearer token; a name taken is refused on the page; Delete asks first, Keep
// keeps it, Delete revokes it, and a revoked token no longer gets in. Every step checked on the page and the server.

const NAME = "e2e-assistant"

const asBearer = async (base, token) => (await fetch(`${base}/api/q/status`, { headers: { authorization: `Bearer ${token}` } })).status

export default [
  {
    name: "a read-only token is made, shown once, listed as 'Can only read', and lets a request in",
    async run({ open, type, click, has, text, until, q, expect, base }) {
      await open("/settings/tokens")
      await has("Make a token")
      await type("Token name", NAME)
      await click("Read only")
      await click("Make token")
      const shown = await until(`[...document.querySelectorAll("code")].map((c) => c.innerText).find((t) => t.startsWith("fr_"))`, 10_000, "the new token on the page")
      await has("Copy it now; it isn’t shown again.")
      const listed = (await q("tokens")).find((t) => t.name === NAME)
      expect(listed, "the server has no such token")
      expect(listed.scope === "read", `made as ${listed.scope}, not read`)
      expect(listed.last_used === null, "a token just made was already used")
      await open("/settings/tokens") // read again: the list doesn't refresh by itself (the BUG test below)
      await has(NAME)
      expect((await text()).includes("Can only read"), "the row doesn't say what the token may do")
      expect((await text()).includes("never used"), "a token not used yet isn't said to be never used")
      expect((await asBearer(base, shown)) === 200, "the token shown didn't let a request in")
      expect((await asBearer(base, `${shown}x`)) === 401, "a wrong token was let in")
      const write = await fetch(`${base}/api/c/add`, { method: "POST", headers: { authorization: `Bearer ${shown}`, "content-type": "application/json" }, body: JSON.stringify({ title: "e2e by token" }) })
      expect(write.status === 403, `a read-only token made a change (${write.status})`)
      expect(!(await q("items", { status: "all" })).some((i) => i.title === "e2e by token"), "the read-only token's add went in")
      await open("/settings/tokens")
      await has("last used today")
      expect((await q("tokens")).find((t) => t.name === NAME).last_used, "its use wasn't noted on the server")
    },
  },
  {
    name: "a name already taken can't be made again: the page says so and the button is off",
    async run({ open, type, has, until, q, expect }) {
      await open("/settings/tokens")
      await has(NAME)
      await type("Token name", NAME)
      await has(`There's already a token called ${NAME}.`)
      const off = await until(`(() => { const b = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Make token"); return b && b.disabled })()`)
      expect(off, "Make token is pressable for a name taken")
      expect((await q("tokens")).filter((t) => t.name === NAME).length === 1, "two tokens of one name")
    },
  },
  {
    name: "a read-and-change token says so; Delete asks first and Keep keeps it",
    async run({ open, type, click, has, text, until, q, expect }) {
      await open("/settings/tokens")
      await type("Token name", "e2e-script")
      await click("Read and change")
      await click("Make token")
      await until(`[...document.querySelectorAll("code")].some((c) => c.innerText.startsWith("fr_"))`, 10_000, "the new token on the page")
      expect((await q("tokens")).find((t) => t.name === "e2e-script")?.scope === "read-write", "not made read-write")
      await open("/settings/tokens")
      await has("Can read and make changes")
      await has("2 in use")
      await click("Delete e2e-script")
      await has("Delete e2e-script?")
      await click("Keep")
      expect(!(await text()).includes("Delete e2e-script?"), "Keep didn't close the question")
      expect((await q("tokens")).some((t) => t.name === "e2e-script"), "Keep deleted it")
    },
  },
  {
    // 24 Nov, found writing this test: token_add is an unlogged command (its result is a secret), and the server
    // announces only logged ones (server/app.py execute → announce), while the page refreshes itself only when the
    // live stream is down (hooks/useCommand.ts). So with the stream up, Make token shows the token but "Your tokens"
    // doesn't list it until the page is read again. ai_key_set, mail_app_set and mail_app_forget are the same.
    name: "a token made is listed in Your tokens at once, without reading the page again (fixed 24 Nov)",
    async run({ open, type, click, has, q, expect }) {
      await open("/settings/tokens")
      await type("Token name", "e2e-listed")
      await click("Make token")
      await has("e2e-listed")
      expect((await q("tokens")).some((t) => t.name === "e2e-listed"), "not made")
    },
  },
  {
    name: "Delete revokes a token: gone from the page and the server, and it no longer gets in",
    async run({ open, click, has, until, q, c, expect, base }) {
      const made = await c("token_add", { name: "e2e-doomed", scope: "read" })
      expect((await asBearer(base, made.result.token)) === 200, "the token made didn't get in")
      await open("/settings/tokens")
      await has("e2e-doomed")
      await click("Delete e2e-doomed")
      await has("Delete e2e-doomed?")
      await click("Delete")
      await until(`!document.body.innerText.includes("e2e-doomed")`, 10_000, "e2e-doomed gone from the page")
      expect(!(await q("tokens")).some((t) => t.name === "e2e-doomed"), "the server still has it")
      expect((await asBearer(base, made.result.token)) === 401, "a revoked token still gets in")
    },
  },
  {
    name: "Delete all asks, then revokes every token and the page says nothing can get in",
    async run({ open, click, has, until, q, expect }) {
      await open("/settings/tokens")
      const count = (await q("tokens")).length
      expect(count >= 2, `only ${count} tokens to delete`)
      await click("Delete all")
      await has(`Delete all ${count}?`)
      await click("Delete")
      await until(`document.body.innerText.includes("No tokens. Nothing outside this app can get in.")`, 15_000, "the empty list")
      expect((await q("tokens")).length === 0, "the server still has tokens")
    },
  },
]
