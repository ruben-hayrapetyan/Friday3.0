// Calendar repeats brought in (tests/features.toml: repeats): a repeating event on a calendar Friday reads but doesn't
// plan around yet waits in the Inbox, with when it is and where from; "I go" brings it in as one weekly repeat with
// the tag picked, "I don't go" leaves it out with its later weeks; Settings → Repeating lists what's waiting to import
// at once. The repeating events come from a calendar of the Mac app's (`mac_sync`, as the Mac app sends it).

const MAC = { "X-Friday-Client": "mac" }
const CAL = "e2e-studio"
const waitFor = async (check, ms = 90_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 500))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const p = (n) => String(n).padStart(2, "0")
/** `days` from now at `hh:mm`, local, with its offset, as EventKit gives it. */
const zoned = (days, hh, mm = 0) => {
  const d = new Date(Date.now() + days * 86_400_000)
  d.setHours(hh, mm, 0, 0)
  const off = -d.getTimezoneOffset()
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(hh)}:${p(mm)}:00${off >= 0 ? "+" : "-"}${p(Math.floor(Math.abs(off) / 60))}:${p(Math.abs(off) % 60)}`
}
/** A weekly event for four weeks from `first` days on: its occurrences. */
const weekly = (series, title, first, hh, minutes) =>
  [0, 7, 14, 21].map((d) => ({ id: `${series}-${d}`, calendar: CAL, title, series, start: zoned(first + d, hh), end: zoned(first + d, hh + Math.floor(minutes / 60), minutes % 60) }))

async function sync(request, events) {
  const now = Date.now()
  const body = { calendars: [{ id: CAL, name: "E2E Studio", account: "iCloud", type: "caldav", color: "#3a5a8c" }], events, since: new Date(now - 7 * 86_400_000).toISOString(), until: new Date(now + 35 * 86_400_000).toISOString() }
  const r = await request("POST", "/api/c/mac_sync", body, MAC)
  if (r.status !== 200) throw new Error(`mac_sync: ${JSON.stringify(r)}`)
}
const waiting = async (q) => Object.fromEntries((await q("calendar_repeats")).map((r) => [r.title, r]))
const POTTERY = weekly("e2e-pottery", "E2E Pottery", 1, 10, 60)
const EVENTS = [...weekly("e2e-ceramics", "E2E Ceramics", 2, 18, 90), ...weekly("e2e-choir", "E2E Choir", 3, 19, 60)]

export default [
  {
    name: "repeating events on a calendar read but not planned around wait as one repeat each",
    async run({ q, c, request, expect }) {
      await sync(request, [])
      await c("calendar_set", { id: CAL, mac: true, on: true, trusted: false })
      await sync(request, EVENTS)
      const found = await waitFor(async () => {
        const w = await waiting(q)
        return w["E2E Ceramics"] && w["E2E Choir"] && w
      })
      expect(found, `not waiting: ${JSON.stringify(Object.keys((await waiting(q)) ?? {}))}`)
      expect(found["E2E Ceramics"].calendar === "E2E Studio" && found["E2E Ceramics"].count === 4, JSON.stringify(found["E2E Ceramics"]))
      expect(/^Every \w+, 6pm–7:30pm$/.test(found["E2E Ceramics"].pattern), found["E2E Ceramics"].pattern)
    },
  },
  {
    name: "in the Inbox, I go brings one in with the tag picked: one weekly repeat, its times planned around",
    async run({ open, click, has, gone, q, c, expect }) {
      const tag = (await q("areas"))[0]?.name ?? (await c("area_add", { name: "E2E Arts" }), "E2E Arts")
      await open("/inbox")
      await click("E2E Ceramics")
      await has("A repeating event on your calendar", "div.fr-gutter")
      await has("Friday isn’t planning around it yet, so work can land in its time. Do you go?")
      await has("E2E Studio", "div.fr-gutter")
      await click("Tag for E2E Ceramics…")
      await click(tag)
      await click("I go: plan around it")
      await has("E2E Ceramics is in your plan")
      expect(await waitFor(async () => !(await waiting(q))["E2E Ceramics"]), "it's still waiting")
      const series = (await q("series_list")).filter((s) => s.title === "E2E Ceramics")
      expect(series.length === 1 && series[0].area === tag, `repeats made: ${JSON.stringify(series)}`)
      const times = await waitFor(async () => {
        const f = (await q("plan", { start: `${new Date().toISOString().slice(0, 10)}T00:00`, end: zoned(30, 23).slice(0, 16) })).fixed.filter((e) => e.title === "E2E Ceramics")
        return f.length >= 3 && f
      })
      expect(times && times.every((e) => e.area === tag && e.start.endsWith("T18:00") && e.end.endsWith("T19:30")), `its times: ${JSON.stringify(times)}`)
      await gone("E2E Ceramics", "[role=list]")
    },
  },
  {
    name: "I don't go leaves it out, its later weeks too, and it stays out when the calendar is read again",
    async run({ open, click, has, q, request, expect }) {
      await open("/inbox")
      await click("E2E Choir")
      await click("I don’t go: leave it out")
      await has("Left out E2E Choir, its later weeks too")
      expect(await waitFor(async () => !(await waiting(q))["E2E Choir"]), "it's still waiting")
      // read again, with a new repeating event on it: once that's waiting, the calendar has been read
      await sync(request, [...EVENTS, ...POTTERY])
      expect(await waitFor(async () => (await waiting(q))["E2E Pottery"]), "the calendar wasn't read again")
      expect(!(await waiting(q))["E2E Choir"], "read again, it's waiting again")
      const planned = (await q("plan")).fixed.filter((e) => e.title === "E2E Choir")
      expect(!planned.length, `planned around anyway: ${JSON.stringify(planned)}`)
    },
  },
  {
    name: "Settings → Repeating lists what's waiting and imports it at once",
    async run({ open, click, has, gone, q, expect }) {
      expect((await waiting(q))["E2E Pottery"], "E2E Pottery isn't waiting")
      const all = await q("calendar_repeats")
      await open("/settings/repeating")
      await has(`${all.length} repeating ${all.length === 1 ? "event" : "events"} in your Google calendars`)
      await has("E2E Pottery")
      await click(`Import ${all.length === 1 ? "it" : `all ${all.length}`}`)
      await has(`Imported ${all.length} repeat`)
      expect(await waitFor(async () => (await q("calendar_repeats")).length === 0), "still waiting after Import")
      expect((await q("series_list")).some((s) => s.title === "E2E Pottery"), "E2E Pottery isn't a repeat")
      await gone("E2E Pottery", ".fr-well")
    },
  },
  {
    name: "the server refuses what isn't waiting any more, and nothing at all",
    async run({ request, expect }) {
      const gone = await request("POST", "/api/c/repeats_import", { repeats: [{ batch: "repeat:e2e-ceramics" }] })
      expect(gone.status === 422 && gone.body.message.includes("isn't waiting any more"), JSON.stringify(gone))
      const out = await request("POST", "/api/c/repeats_leave_out", { batch: "repeat:nothing" })
      expect(out.status === 422 && out.body.message.includes("isn't waiting any more"), JSON.stringify(out))
      const empty = await request("POST", "/api/c/repeats_import", { repeats: [] })
      expect(empty.status === 422, JSON.stringify(empty))
    },
  },
  {
    name: "an event time the Mac app sends that isn't a time is refused, naming the event (fixed 24 Nov)",
    async run({ request, day, expect }) {
      // found writing these tests: a time like 18:90 was taken, and every later read of its calendar failed
      const calendar = { id: "e2e-cal", name: "E2E Studio", type: "local" }
      const at = (h) => `${day(1)}T${h}:00-05:00`
      const sent = await request("POST", "/api/c/mac_sync", {
        calendars: [calendar], since: `${day(0)}T00:00:00-05:00`, until: `${day(7)}T00:00:00-05:00`,
        events: [{ id: "e2e-bad", calendar: "e2e-cal", title: "Bad studio", start: at("18:00"), end: at("18:90") }],
      })
      expect(sent.status === 422 && JSON.stringify(sent.body).includes("Bad studio"), `taken: ${JSON.stringify(sent)}`)
    },
  },
]
