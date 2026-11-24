// Sleep (tests/features.toml: sleeping): Insights → Sleep's switch; a tap made now; a night you didn't tap logged from
// its row, then a time in it changed and one cleared; and a sleep tap the Inbox asks about, answered "I don't
// remember". Every step checked on the page and on the server (the sleep view, a day's review).

/** Until `check()` is truthy, within ten seconds. */
async function eventually(check, said, wait) {
  for (let end = Date.now() + 10_000; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited 10s for ${said}`)
  }
}

const nightOf = async (q, date) => (await q("sleep")).nights.find((n) => n.date === date)

/** The `n`th night's row button (0: last night), clicked; its evening's date. */
const openNight = (until, n) =>
  until(`(() => { const rows = [...document.querySelectorAll('button[title="Change this night"]')]; const b = rows[${n}]; if (!b) return false; b.click(); return true })()`, 10_000, `night row ${n}`)

/** A date `n` days from `from` (YYYY-MM-DD). */
function addDays(from, n) {
  const d = new Date(`${from}T12:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const today = (day) => (new Date().getHours() < 4 ? day(-1) : day(0)) // Friday's day starts at 4am

export default [
  {
    name: "Insights → Sleep: off, its switch turns tracking on, and the taps and your nights show",
    async run({ open, click, has, until, q, c, expect, wait }) {
      await c("settings_set", { key: "sleep_tracking", value: { on: false } })
      await open("/insights?tab=sleep")
      await has("Off. Turn it on and the Now bar offers")
      await click("Track my sleep")
      await eventually(async () => (await q("settings")).sleep_tracking.on === true, "tracking on, on the server", wait)
      await has("Your nights")
      for (const tap of ["Done with work", "Going to bed", "I'm up", "Ready to work"]) await has(tap)
      expect((await q("sleep")).on === true, "the sleep view is still off")
      const rows = await until(`document.querySelectorAll('button[title="Change this night"]').length`, 10_000, "the nights")
      expect(rows === 14, `${rows} nights listed, not the last two weeks`)
    },
  },
  {
    name: "a tap made now is recorded, and taken back it's gone",
    async run({ open, click, has, q, c, expect, wait }) {
      await open("/insights?tab=sleep")
      await has("Missed a tap in the Now bar? Make it here.")
      const before = (await q("sleep")).nights.filter((n) => n.done).length
      await click("Done with work")
      await has("Done with work: ")
      const found = await eventually(async () => (await q("sleep")).nights.find((n) => n.done && Date.now() - new Date(n.done).getTime() < 5 * 60_000), "the tap on the server", wait)
      expect((await q("sleep")).nights.filter((n) => n.done).length === before + 1, "not one more night with Done with work")
      await c("sleep_mark_remove", { id: found.done_id }) // tidy: no tap left for the next tests
    },
  },
  {
    name: "a night not tapped is logged from its row; a time in it changed; one cleared",
    async run({ open, click, type, has, until, q, day, expect, wait }) {
      await open("/insights?tab=sleep")
      await has("Your nights")
      // the first night that isn't recorded, from four nights back
      const n = await until(`(() => { const rows = [...document.querySelectorAll('button[title="Change this night"]')]; const i = rows.findIndex((b, i) => i >= 3 && b.innerText.includes("Not recorded")); return i >= 0 ? i + 1 : false })()`, 10_000, "a night not recorded")
      const evening = addDays(today(day), -n)
      const morning = addDays(evening, 1)
      await openNight(until, n - 1)
      await has("Log it")
      await type("Went to bed", "11:15pm")
      await type("Got up", "7:00am", { enter: true }) // Enter in a time saves, as Log it does
      const logged = await eventually(async () => (await nightOf(q, evening))?.up, "the night on the server", wait)
      expect(logged === `${morning}T07:00`, `up at ${logged}, not 7am`)
      const night = await nightOf(q, evening)
      expect(night.bed === `${evening}T23:15` && night.slept_min === 465, `the night: ${JSON.stringify(night)}`)
      await has("7h 45m")
      // changed: up at 6:30
      await openNight(until, n - 1)
      await has("Save changes")
      await type("Got up", "6:30am", { enter: true })
      await eventually(async () => (await nightOf(q, evening))?.up === `${morning}T06:30`, "the new time on the server", wait)
      const moved = await nightOf(q, evening)
      expect(moved.up_id === night.up_id && moved.slept_min === 435, `moved, not made again: ${JSON.stringify(moved)}`)
      await has("7h 15m")
      // cleared: no bedtime
      await openNight(until, n - 1)
      await click("Clear went to bed")
      await click("Save changes")
      await eventually(async () => (await nightOf(q, evening))?.bed === null, "the bedtime gone on the server", wait)
      expect((await nightOf(q, evening)).slept_min === null, "still counts a sleep with no bedtime")
    },
  },
  {
    name: "a sleep tap the Inbox asks about, answered I don't remember, isn't asked again",
    async run({ open, click, has, until, q, day, expect, wait }) {
      const days = [addDays(today(day), -1), today(day)]
      const asked = async () => (await Promise.all(days.map((d) => q("review", { date: d })))).flatMap((r) => r.sleep)
      const before = await asked()
      expect(before.length > 0, "the Inbox asks no sleep taps (tracking on, yesterday untapped)")
      await open("/inbox")
      await has("A sleep tap you missed")
      const first = await until(`(() => { const row = [...document.querySelectorAll("[role=listitem]")].find((r) => r.innerText.includes("A sleep tap you missed")); if (!row) return false; row.click(); return row.innerText.split("\\n")[0].trim() })()`, 10_000, "a sleep row")
      await has("It starts from your usual time.")
      await click("I don't remember")
      const after = await eventually(async () => {
        const now = await asked()
        return now.length === before.length - 1 && now
      }, "one fewer sleep tap asked", wait)
      const gone = before.find((a) => !after.some((b) => b.kind === a.kind && b.date === a.date))
      expect(gone && gone.question === first, `skipped "${gone?.question}", the row said "${first}"`)
    },
  },
]
