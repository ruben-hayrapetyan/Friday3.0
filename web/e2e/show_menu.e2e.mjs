// The Plan page's Show menu (tests/features.toml: calendars): every calendar listed, a long name cut with "…" on its
// line and whole on hover, never running out of the menu over its shortcut (27 Nov, a user's notes, "Friday
// Notes-3": "anonymous.dragon.888@gmail.com" and "Holidays in United States (anonymous.dragon.888@gmail.com)" ran out
// of the box). The layout check after each click (scripts/browser.mjs LAYOUT) says so of any menu whose words run out.

const MAC = { "X-Friday-Client": "mac" }
const LONG = "Holidays in United States (anonymous.dragon.888@gmail.com)"
const EMAIL = "anonymous.dragon.888@gmail.com"

export default [
  {
    name: "a calendar with a long name is listed in Show cut to its line, its whole name on hover, nothing running out",
    async run({ open, click, until, evaluate, request, c, q, expect }) {
      const calendars = [
        { id: "e2e-long-holidays", name: LONG, account: "iCloud", type: "subscription", color: "#3a5a8c" },
        { id: "e2e-long-email", name: EMAIL, account: "iCloud", type: "caldav", color: "#5a8c3a" },
      ]
      const now = Date.now()
      const r = await request("POST", "/api/c/mac_sync", { calendars, events: [], since: new Date(now - 86_400_000).toISOString(), until: new Date(now + 14 * 86_400_000).toISOString() }, MAC)
      expect(r.status === 200, `mac_sync: ${JSON.stringify(r)}`)
      for (const cal of calendars) await c("calendar_set", { id: cal.id, mac: true, on: true, trusted: false })
      const look = (await q("settings")).calendar_look ?? {}
      await c("settings_set", { key: "calendar_look", value: { ...look, toolbar: [LONG, EMAIL, ...(look.toolbar ?? [])].slice(0, 9) } })
      await open("/")
      await click("Show") // the layout check runs after it: words running out of the menu fail here
      const name = await until(`(() => {
        const menu = document.querySelector("[data-menu]")
        const el = menu && [...menu.querySelectorAll("span")].find((s) => s.getAttribute("title") === ${JSON.stringify(LONG)})
        if (!el) return null
        const m = menu.getBoundingClientRect(), r = el.getBoundingClientRect(), c = getComputedStyle(el)
        return JSON.stringify({ inside: r.right <= m.right + 1 && r.left >= m.left - 1, cut: c.textOverflow, one: c.whiteSpace })
      })()`, 15_000, "the long calendar in the Show menu")
      const got = JSON.parse(name)
      expect(got.inside, `the long name runs out of the menu: ${name}`)
      expect(got.cut === "ellipsis" && got.one === "nowrap", `the long name isn't cut to its line: ${name}`)
      await evaluate(`document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))`)
    },
  },
]
