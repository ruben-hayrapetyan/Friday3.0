// Settings, paces and one-day changes (tests/features.toml: settings): Settings → Schedule's choices (the default
// pace, the week's first day, sittings, each day's limit), the Plan menu's Pace (a pace for three days, previewed and
// applied), and Advanced's saved paces (saved from the dials in use, then deleted). Each pressed or typed as a person
// would; the page's choice and the server's settings, paces and calendar checked after each; each put back after.

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

/** Whether the choice (a Seg button) named `name` shows as chosen. */
const chosen = (name) => `[...document.querySelectorAll(".fr-seg button")].some((b) => b.textContent.trim() === ${JSON.stringify(name)} && b.getAttribute("aria-pressed") === "true")`

const settings = (q) => q("settings")

export default [
  {
    name: "Schedule: the default pace, the week's first day and sittings are saved on the server as picked",
    async run({ open, click, until, q, wait, expect }) {
      await open("/settings/schedule")
      await click("Push")
      await eventually(async () => (await settings(q)).pace.default === "Push", 10_000, "the default pace Push on the server", wait)
      await until(chosen("Push"), 5_000, "Push shown as chosen")
      expect((await q("paces")).default === "Push", "paces doesn't say Push is the default")
      await click("Sunday")
      await eventually(async () => (await settings(q)).time.week_start === "sun", 10_000, "the week starting Sunday", wait)
      await click("In one go")
      await eventually(async () => (await settings(q)).sittings.one_go === true, 10_000, "sittings in one go", wait)
      // put back, from the page
      await click("Normal")
      await click("Monday")
      await click("Split as needed")
      await eventually(async () => {
        const s = await settings(q)
        return s.pace.default === "Normal" && s.time.week_start === "mon" && s.sittings.one_go === false
      }, 10_000, "the choices put back", wait)
    },
  },
  {
    name: "Schedule → Set each day: one day's limit typed is that weekday's cap on the server and the calendar",
    async run({ open, click, type, q, c, wait, expect }) {
      const before = (await settings(q)).daily_cap
      await open("/settings/schedule")
      await click("Set each day")
      await type("wed limit", "3.5", { enter: true })
      await eventually(async () => (await settings(q)).daily_cap.wed === 3.5, 10_000, "Wednesday's limit 3.5 on the server", wait)
      const caps = (await settings(q)).daily_cap
      expect(Object.entries(caps).every(([d, h]) => d === "wed" || h === before[d]), `other days changed: ${JSON.stringify(caps)}`)
      const days = (await q("calendar", { days: 7 })).days
      for (const d of days) {
        const wednesday = new Date(`${d.date}T12:00Z`).getUTCDay() === 3
        expect(wednesday ? d.cap_hours === 3.5 : d.cap_hours === before[["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date(`${d.date}T12:00Z`).getUTCDay()]], `${d.date}'s cap on the calendar is ${d.cap_hours}`)
      }
      await c("settings_set", { key: "daily_cap", value: before })
    },
  },
  {
    name: "the Plan menu's Pace: Easy for 3 days, previewed, applied, is the pace on the server and the calendar",
    async run({ open, click, has, until, q, c, planned, expect }) {
      await planned()
      await open("/")
      await click("Plan…")
      await click("Pace")
      await has("How hard Friday pushes for a while")
      await click("Easy")
      await click("3 days")
      await until(`(() => { const b = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Apply pace"); return b && !b.disabled })()`, 120_000, "the preview done and Apply pace ready")
      await click("Apply pace")
      await has("Easy pace, today through")
      try {
        const paces = await q("paces")
        const cal = await q("calendar", { days: 4 })
        const today = cal.today
        const last = new Date(Date.parse(`${today}T12:00Z`) + 2 * 86_400_000).toISOString().slice(0, 10)
        expect(paces.now_label === "Easy" && paces.period_end === last, `the server's pace is ${paces.now_label} until ${paces.period_end}, not Easy until ${last}`)
        expect(JSON.stringify(cal.days.map((d) => d.pace)) === JSON.stringify(["Easy", "Easy", "Easy", null]), `the calendar's paces: ${cal.days.map((d) => d.pace)}`)
      } finally {
        await c("pace", { name: "Normal" })
      }
    },
  },
  {
    name: "Advanced: a pace saved from the dials in use is on the server, and its Delete takes it off",
    async run({ open, click, type, has, until, q, wait, expect }) {
      await open("/settings/advanced")
      await has("Saved paces")
      await type("New pace", "E2E exam week")
      await click("Save the dials in use")
      const saved = await eventually(async () => (await q("paces")).paces["E2E exam week"], 10_000, "the pace on the server", wait)
      const now = (await q("paces")).now_dials
      expect(JSON.stringify(saved) === JSON.stringify(now), `saved ${JSON.stringify(saved)}, the dials in use are ${JSON.stringify(now)}`)
      await has("E2E exam week")
      await click("Delete E2E exam week")
      await eventually(async () => !(await q("paces")).paces["E2E exam week"], 10_000, "the pace gone from the server", wait)
      await until(`![...document.querySelectorAll("[aria-label]")].some((el) => el.getAttribute("aria-label") === "Delete E2E exam week")`, 10_000, "its row gone")
      expect(!(await q("paces")).paces["E2E exam week"], "the pace is still saved")
      // the default and the pace in use have no Delete
      const paces = await q("paces")
      await until(`![...document.querySelectorAll("[aria-label]")].some((el) => el.getAttribute("aria-label") === ${JSON.stringify(`Delete ${paces.default}`)})`, 2_000, "no Delete on the default")
    },
  },
]
