// Naps (tests/features.toml: napping), in Insights → Sleep: with sleep tracking on, Taking a nap starts one and I'm
// up ends it; Log a nap logs one you didn't tap, on the day you pick; a nap clicked opens its card to change its times
// or delete it; every step read back from the server, and its refusals.

const sleep = async (q) => await q("sleep")
const waitFor = async (check, ms = 10_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const PAGE = "/insights?tab=sleep"
/** Clicks the first `css` element showing `words` (a nap's row, named by its day and times). */
const pick = (until, css, words) =>
  until(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(css)})].find((e) => e.innerText.replace(/\\s+/g, " ").includes(${JSON.stringify(words)})); if (!el) return false; el.click(); return true })()`, 10_000, `${css} with "${words}"`)
const ROW = "button[title='Change this nap']"
let tracking // the sample's own switch, put back at the end

export default [
  {
    name: "Track my sleep turns tracking on, and the taps and Log a nap show",
    async run({ open, click, has, q, expect }) {
      tracking = (await q("settings")).sleep_tracking
      await open(PAGE)
      if (!tracking.on) {
        await has("Track my sleep")
        await click("Track my sleep")
        expect(await waitFor(async () => (await q("settings")).sleep_tracking.on), "the switch didn't turn tracking on")
      }
      await has("Missed a tap in the Now bar? Make it here.")
      await has("Your naps")
      await has("Log a nap")
      expect((await sleep(q)).on, "the server's sleep says tracking is off")
    },
  },
  {
    name: "Taking a nap starts one; I'm up ends it, and it's listed today",
    async run({ open, click, has, q, c, expect }) {
      const before = (await sleep(q)).naps.length
      await open(PAGE)
      await click("Taking a nap")
      await has("Napping since")
      const napping = await waitFor(async () => (await sleep(q)).napping)
      expect(napping, "the server has no nap going")
      // ended within the minute it started would be refused ("that's before you lay down"): it began 5 minutes ago
      const p = (n) => String(n).padStart(2, "0")
      const d = new Date(Date.now() - 5 * 60_000)
      await c("nap_edit", { id: napping.id, start: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}` })
      await open(PAGE)
      await click("I’m up") // the nap's (curly), not the morning tap "I'm up"
      await has("Taking a nap")
      const after = await waitFor(async () => {
        const s = await sleep(q)
        return !s.napping && s.naps.length === before + 1 && s
      })
      expect(after, "the nap wasn't ended and kept")
      const nap = after.naps.find((n) => n.id === napping.id)
      expect(nap?.end && nap.minutes >= 5 && nap.minutes <= 6, `the nap kept: ${JSON.stringify(nap)}`)
    },
  },
  {
    name: "Log a nap logs yesterday's, listed with its length; its card changes its end, then deletes it",
    async run({ open, click, type, press, has, gone, until, q, day, expect }) {
      await open(PAGE)
      await click("Log a nap")
      await has("Lay down")
      await click("Day…")
      await click("Yesterday")
      await type("Lay down", "2:00pm")
      await type("Got up", "2:45pm")
      await press("Enter")
      await has("Logged a nap")
      const logged = await waitFor(async () => (await sleep(q)).naps.find((n) => n.start === `${day(-1)}T14:00`))
      expect(logged, `no nap yesterday at 2pm: ${JSON.stringify((await sleep(q)).naps)}`)
      expect(logged.end === `${day(-1)}T14:45` && logged.minutes === 45, `logged as ${JSON.stringify(logged)}`)
      await has("2:00pm–2:45pm")
      await pick(until, ROW, "2:00pm–2:45pm")
      await has("Nap ·")
      await type("Got up", "3:15pm")
      await press("Enter")
      await has("Nap now")
      const edited = await waitFor(async () => (await sleep(q)).naps.find((n) => n.id === logged.id && n.end === `${day(-1)}T15:15`))
      expect(edited?.minutes === 75, `edited to ${JSON.stringify(edited)}`)
      await has("2:00pm–3:15pm")
      await pick(until, ROW, "2:00pm–3:15pm")
      await click("Delete this nap")
      await has("Removed the nap")
      expect(await waitFor(async () => !(await sleep(q)).naps.some((n) => n.id === logged.id)), "the nap is still on the server")
      await gone("2:00pm–3:15pm")
    },
  },
  {
    name: "the server refuses a nap that ends first, one over four hours, ending one not going and changing one not there",
    async run({ request, day, expect }) {
      const post = (name, body) => request("POST", `/api/c/${name}`, body)
      const back = await post("nap_log", { start: `${day(-2)}T15:00`, end: `${day(-2)}T14:00` })
      expect(back.status === 422 && back.body.message.includes("a nap ends after it starts, within four hours"), JSON.stringify(back))
      const long = await post("nap_log", { start: `${day(-2)}T09:00`, end: `${day(-2)}T14:00` })
      expect(long.status === 422 && long.body.field === "end", JSON.stringify(long))
      const ahead = await post("nap_log", { start: `${day(2)}T14:00`, end: `${day(2)}T14:30` })
      expect(ahead.status === 422 && ahead.body.message.includes("later than now"), JSON.stringify(ahead))
      const up = await post("nap_end", {})
      expect(up.status === 422 && up.body.message.includes("you aren't napping"), JSON.stringify(up))
      for (const name of ["nap_edit", "nap_remove"]) {
        const none = await post(name, name === "nap_edit" ? { id: 999_999, start: `${day(-1)}T14:00` } : { id: 999_999 })
        expect(none.status === 422 && none.body.message.includes("no nap 999999"), `${name}: ${JSON.stringify(none)}`)
      }
    },
  },
  {
    name: "tracking off, naps are refused and the page says it's off",
    async run({ open, click, has, q, c, request, expect }) {
      await open(PAGE)
      await click("Track my sleep")
      expect(await waitFor(async () => !(await q("settings")).sleep_tracking.on), "the switch didn't turn tracking off")
      await has("Off. Turn it on and the Now bar offers")
      const refused = await request("POST", "/api/c/nap_start", {})
      expect(refused.status === 422 && refused.body.message.includes("sleep tracking is off"), JSON.stringify(refused))
      if (tracking?.on) await c("settings_set", { key: "sleep_tracking", value: tracking })
    },
  },
]
