// Google calendars (tests/features.toml: calendars): Settings → Calendars lists the calendars read; Integrations →
// Google Calendar folds every calendar under "N of M read", each with a switch to read it, how its events are read,
// whether they skip the Inbox. Switching one off takes its events off the plan, on again brings them back; each choice
// is checked on the page and on the server (google_calendars, the plan's events).

const clubs = async (q) => (await q("google_calendars")).find((c) => c.name === "Clubs")
const clubEvents = async (q) => (await q("plan")).fixed.filter((f) => f.calendar === "Clubs")
const settle = async (check, what) => {
  for (let i = 0; i < 60; i++, await new Promise((r) => setTimeout(r, 250))) if (await check()) return
  throw new Error(`waited 15s for ${what}`)
}

const openList = async ({ open, type, click, has }) => {
  await open("/settings/integrations")
  await type("Search integrations", "google calendar")
  await click("Google Calendar")
  await has("Events become fixed time.")
  await click("Calendars7 of 7|Calendars6 of 7")
  await has("Read events as")
}

export default [
  {
    name: "Settings → Calendars lists every Google calendar read, as the server has them",
    async run({ open, has, q, expect }) {
      const read = (await q("google_calendars")).filter((c) => c.on)
      expect(read.length >= 2, `only ${read.length} calendars read in the sample`)
      await open("/settings/calendars")
      await has("Your calendars")
      for (const c of read) await has(c.name)
    },
  },
  {
    name: "switching Clubs off stops reading it: its events leave the plan and the list says 6 of 7",
    async run(t) {
      const { click, has, until, q, open, text, expect } = t
      expect((await clubs(q)).on, "Clubs isn't read to begin with")
      const before = await clubEvents(q)
      expect(before.length > 0, "the sample's plan has no Clubs events")
      await openList(t)
      await click("Read Clubs")
      await has("Stopped reading Clubs")
      await settle(async () => (await clubs(q)).on === false, "Clubs off on the server")
      await until(`document.querySelector('[role=switch][aria-label="Read Clubs"]')?.getAttribute("aria-checked") === "false"`, 10_000, "Clubs' switch off")
      await has("6 of 7 read")
      await settle(async () => (await clubEvents(q)).length === 0, "Clubs' events off the plan")
      for (const e of before) {
        const status = (await q("item", { id: e.id })).item.status
        expect(status === "dropped", `${e.title} on ${e.start} is ${status}, not put away`)
      }
      await open("/settings/calendars")
      await has("Your calendars")
      await has("Canvas")
      expect(!(await text()).includes("Clubs"), "Settings → Calendars still lists Clubs")
    },
  },
  {
    name: "switching Clubs on again brings its events back to the plan",
    async run(t) {
      const { click, has, until, q, expect } = t
      await openList(t)
      await click("Read Clubs")
      await has("Reading Clubs")
      await settle(async () => (await clubs(q)).on === true, "Clubs on on the server")
      await until(`document.querySelector('[role=switch][aria-label="Read Clubs"]')?.getAttribute("aria-checked") === "true"`, 10_000, "Clubs' switch on")
      await settle(async () => (await clubEvents(q)).length > 0, "Clubs' events back on the plan")
      expect((await clubEvents(q)).every((e) => e.status === "todo"), "an event brought back isn't to do")
    },
  },
  {
    name: "how Clubs is read and whether it skips the Inbox are saved from its row",
    async run(t) {
      const { click, has, until, q, expect } = t
      const kinds = Object.keys((await q("settings")).presets)
      const kind = kinds.find((k) => /club|event|social/i.test(k)) ?? kinds[0]
      await openList(t)
      await click("How Clubs is read")
      await until(`!!document.querySelector('[role=listbox][aria-label="How Clubs is read"]')`, 10_000, "the kinds menu")
      await click(kind)
      await has(`Saved Clubs`)
      await settle(async () => (await clubs(q)).kind === kind, `Clubs read as ${kind}`)
      const trusted = (await clubs(q)).trusted
      await click("Clubs straight to the plan")
      await settle(async () => (await clubs(q)).trusted === !trusted, "Skip Inbox switched on the server")
      await until(`document.querySelector('[role=switch][aria-label="Clubs straight to the plan"]')?.getAttribute("aria-checked") === "${!trusted}"`, 10_000, "the Skip Inbox switch")
      await click("How Clubs is read")
      await click("Per event")
      await settle(async () => (await clubs(q)).kind === "auto", "Clubs back to per event")
      await click("Clubs straight to the plan")
      await settle(async () => (await clubs(q)).trusted === trusted, "Skip Inbox back")
    },
  },
]
