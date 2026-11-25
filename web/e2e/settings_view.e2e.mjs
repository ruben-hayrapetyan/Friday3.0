// Reading settings (tests/features.toml: settings_view): Settings opens at Integrations the first time, every section
// opens from its list, the one you were last on is where Settings opens next; Advanced → Every setting lists every key
// the server has and shows each one's value as the server has it; keys friday.toml sets say they're read-only.

const SECTIONS = ["Appearance", "Calendars", "Tags/Kinds", "Schedule", "Repeating", "Breaks", "Integrations", "Phone", "Tokens", "Shortcuts", "Updates", "Advanced"]
const textarea = `document.querySelector("main textarea, textarea")?.value`

export default [
  {
    name: "Settings opens at Integrations the first time, and every section opens from the list",
    async run({ open, until, click, has, text, expect }) {
      await open("/settings")
      await until(`location.hash === "#/settings/integrations"`, 5000, "Settings opening at Integrations")
      await has("Changes apply right away")
      for (const label of SECTIONS) {
        await click(label)
        const id = label === "Tags/Kinds" ? "tags" : label.toLowerCase()
        await until(`location.hash === "#/settings/${id}"`, 5000, `${label} opening`)
        const shown = await text(".fr-gutter")
        expect(shown.trim().length > 20, `${label} shows nothing`)
        expect(!shown.includes("Something on this page broke"), `${label} broke`)
      }
    },
  },
  {
    name: "Settings opens where you last were, and Back to plan goes to the plan",
    async run({ open, until, click }) {
      await open("/settings/schedule")
      await click("Phone")
      await until(`location.hash === "#/settings/phone"`, 5000, "Phone opening")
      await until(`(location.hash = "#/", true)`)
      await until(`!location.hash.startsWith("#/settings")`, 5000, "the plan")
      await until(`(location.hash = "#/settings", true)`)
      await until(`location.hash === "#/settings/phone"`, 5000, "Settings opening at Phone, the last one")
      await click("Back to plan")
      await until(`location.hash === "#/" || location.hash === ""`, 5000, "Back to plan")
    },
  },
  {
    name: "Every setting lists each key the server has, and shows each one's value as the server has it",
    async run({ open, until, click, q, expect }) {
      const settings = await q("settings")
      await open("/settings/advanced")
      await until(`document.querySelectorAll("textarea").length > 0`, 10_000, "the settings editor")
      const keys = await until(`(() => { const b = [...document.querySelectorAll("textarea")][0].closest(".space-y-2")?.firstElementChild?.querySelectorAll("button"); return b && b.length ? [...b].map((x) => x.textContent.trim()) : null })()`)
      expect(JSON.stringify([...keys].sort()) === JSON.stringify(Object.keys(settings).sort()), `keys shown ${keys.length}, server ${Object.keys(settings).length}`)
      const first = JSON.parse(await until(textarea))
      expect(JSON.stringify(first) === JSON.stringify(settings.rules), "the editor doesn't open on the rules as the server has them")
      for (const key of ["sleep", "time", "presets", "phone", "kind_order"]) {
        await click(key)
        await until(`${textarea} === ${JSON.stringify(JSON.stringify(settings[key], null, 2))}`, 5000, `${key} as the server has it`)
      }
    },
  },
  {
    name: "a setting changed on the server reads back changed in Every setting",
    async run({ open, until, click, q, c, expect }) {
      const before = (await q("settings")).kind_order
      const order = [...before].reverse()
      await c("settings_set", { key: "kind_order", value: order })
      try {
        await open("/settings/advanced")
        await until(`document.querySelectorAll("textarea").length > 0`, 10_000, "the settings editor")
        await click("kind_order")
        await until(`${textarea} === ${JSON.stringify(JSON.stringify(order, null, 2))}`, 5000, "the new order")
        expect(JSON.stringify((await q("settings")).kind_order) === JSON.stringify(order), "the server didn't keep the order")
      } finally {
        await c("settings_set", { key: "kind_order", value: before })
      }
    },
  },
  {
    name: "keys friday.toml sets say they're read-only here",
    async run({ open, has, q, answer }) {
      const status = await q("status")
      await answer({ status: { ...status, config_keys: ["sleep", "planner"] } })
      await open("/settings/schedule")
      await has("Set in friday.toml, so read-only here: sleep, planner.")
    },
  },
  {
    name: "Change a Setup answer lists each of Setup's questions, and one opens Setup at it",
    async run({ open, click, has, text, press, gone, expect }) {
      await open("/settings/schedule")
      await click("Change a Setup answer")
      for (const label of ["In school or not", "When you get up", "When you go to bed", "Free weekends", "All of Setup’s questions, in order"]) await has(label)
      await click("When you go to bed")
      await has("bed", "[role=dialog]")
      expect((await text("[role=dialog]")).length > 10, "Setup didn't open")
      await press("Escape")
      await gone("All of Setup’s questions, in order")
    },
  },
]
