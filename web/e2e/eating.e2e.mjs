// Meals (tests/features.toml: eating), in Insights → Meals and the Inbox: Track my meals turns tracking on; Eating now
// and Done eating; a meal logged on a past day from its row, changed and deleted from its chip; a meal said skipped and
// taken back; and what Friday learns from meals logged (a lunch that takes longer, a breakfast at another time) asked
// in the Inbox, and the answer changing the plan's routine. Every step read back from the server, and its refusals.
// What it logs is undone at the end (the sample's other tests plan around its meals).

const PAGE = "/insights?tab=meals"
const meals = async (q) => await q("meals")
const on = async (q, date) => (await meals(q)).days.find((d) => d.date === date)?.meals ?? []
const waitFor = async (check, ms = 15_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const local = (ms) => {
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
/** Clicks the button `words` in the meals row `n` days back (0: today), or anything in it matching `css`. */
const inRow = (until, n, words, css = "button") =>
  until(`(() => { const sec = [...document.querySelectorAll("section")].find((s) => s.innerText.startsWith("Your meals")); const row = sec?.querySelectorAll(":scope > div > .fr-row")[${n}]; const el = row && [...row.querySelectorAll(${JSON.stringify(css)})].find((b) => b.innerText.replace(/\\s+/g, " ").trim().includes(${JSON.stringify(words)})); if (!el) return false; el.click(); return true })()`, 10_000, `"${words}" in the meals ${n} days back`)
/** In the page: the meals row `n` days back, as text. */
const rowJs = (n) => `(() => { const sec = [...document.querySelectorAll("section")].find((s) => s.innerText.startsWith("Your meals")); return sec?.querySelectorAll(":scope > div > .fr-row")[${n}]?.innerText.replace(/\\s+/g, " ") ?? "" })()`
const rowText = (until, n) => until(rowJs(n))
/** "09:45" as the page says it on the 12-hour clock: "9:45am" (":00" left out, as it does). */
const twelve = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number)
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""}${h < 12 ? "am" : "pm"}`
}
const undo = [] // command ids to undo at the end, newest last
let tracking

export default [
  {
    name: "Track my meals turns tracking on; Eating now and the days to log show",
    async run({ open, click, has, q, expect }) {
      tracking = (await q("settings")).meal_tracking
      await open(PAGE)
      if (!tracking.on) {
        await has("Off. Turn it on and the Now bar offers")
        await click("Track my meals")
        expect(await waitFor(async () => (await q("settings")).meal_tracking.on), "the switch didn't turn tracking on")
      }
      await has("Eating now:")
      await has("Your meals")
      for (const k of ["Breakfast", "Lunch", "Dinner", "Snack"]) await has(k, "main")
      expect((await meals(q)).on, "the server's meals say tracking is off")
    },
  },
  {
    name: "Eating now: Snack starts one, Done eating ends it, and today's row shows it",
    async run({ open, click, has, q, c, day, expect }) {
      await open(PAGE)
      await click("Snack")
      await has("Eating snack since")
      const eating = await waitFor(async () => (await meals(q)).eating)
      expect(eating?.kind === "snack", `the server's eating: ${JSON.stringify(eating)}`)
      // ended within the minute it started would be refused ("that's before you started"): it began 20 minutes ago
      await c("meal_edit", { id: eating.id, start: local(Date.now() - 20 * 60_000) })
      await open(PAGE)
      await click("Done eating")
      await has("Snack: 2") // "Snack: 20 min"
      const done = await waitFor(async () => !(await meals(q)).eating && (await on(q, day(0))).find((m) => m.id === eating.id && m.end))
      expect(done && done.minutes >= 20 && done.minutes <= 21, `ended as ${JSON.stringify(done)}`)
      await has("Eating now:")
      expect((await meals(q)).eating === null, "still eating")
      await c("meal_remove", { id: eating.id }) // the sample's today as it was
    },
  },
  {
    name: "a lunch logged two days back from its row, changed from its chip, then deleted",
    async run({ open, press, type, has, until, q, day, expect }) {
      await open(PAGE)
      await has("Your meals")
      const before = await on(q, day(-2))
      expect(!before.some((m) => m.kind === "lunch"), "the sample has lunch two days back already")
      await inRow(until, 2, before.length ? "Lunch" : "Log a meal")
      if (!before.length) await inRow(until, 2, "Lunch")
      await has("Started")
      await type("Started", "12:15pm")
      await type("Finished", "1:05pm")
      await press("Enter")
      await has("Logged lunch")
      const lunch = await waitFor(async () => (await on(q, day(-2))).find((m) => m.kind === "lunch"))
      expect(lunch?.start === `${day(-2)}T12:15` && lunch.end === `${day(-2)}T13:05` && lunch.minutes === 50, `logged as ${JSON.stringify(lunch)}`)
      expect(await until(`${rowJs(2)}.includes("Lunch 12:15pm–1:05pm · 50m")`, 10_000, "the lunch's chip").catch(() => false), `the row: ${await rowText(until, 2)}`)
      await inRow(until, 2, "Lunch 12:15pm")
      await type("Finished", "1:20pm")
      await press("Enter")
      await has("Lunch now")
      const edited = await waitFor(async () => (await on(q, day(-2))).find((m) => m.id === lunch.id && m.end === `${day(-2)}T13:20`))
      expect(edited?.minutes === 65, `changed to ${JSON.stringify(edited)}`)
      await inRow(until, 2, "Lunch 12:15pm")
      await inRow(until, 2, "Delete this meal")
      expect(await waitFor(async () => !(await on(q, day(-2))).some((m) => m.id === lunch.id)), "the lunch is still on the server")
    },
  },
  {
    name: "a dinner said skipped three days back shows skipped; Not skipped after all takes it back",
    async run({ open, has, until, q, day, expect }) {
      await open(PAGE)
      const before = await on(q, day(-3))
      expect(!before.some((m) => m.kind === "dinner"), "the sample has dinner three days back already")
      await inRow(until, 3, before.length ? "Dinner" : "Log a meal")
      if (!before.length) await inRow(until, 3, "Dinner")
      await inRow(until, 3, "I skipped it")
      await has("Skipped dinner")
      const skipped = await waitFor(async () => (await on(q, day(-3))).find((m) => m.kind === "dinner" && m.skipped))
      expect(skipped, "the server has no skipped dinner")
      expect(await until(`${rowJs(3)}.includes("Dinner skipped")`, 10_000, "the skipped dinner's chip").catch(() => false), `the row: ${await rowText(until, 3)}`)
      await inRow(until, 3, "Dinner skipped")
      await has("You said you skipped it")
      await inRow(until, 3, "Not skipped after all")
      expect(await waitFor(async () => !(await on(q, day(-3))).some((m) => m.id === skipped.id)), "the skip is still on the server")
    },
  },
  {
    name: "lunches that take an hour are asked about in the Inbox; Plan 1h plans the routine at an hour",
    async run({ open, click, has, gone, q, c, day, expect }) {
      for (let n = 1; n <= 6; n++) undo.push((await c("meal_log", { kind: "lunch", start: `${day(-n)}T12:00`, end: `${day(-n)}T13:00` })).command_id)
      const change = await waitFor(async () => (await meals(q)).changes.find((x) => x.kind === "lunch"))
      expect(change?.usual_min === 60 && change.new_min === 60 && change.planned_min < 60, `what's learned: ${JSON.stringify(change)}`)
      await open("/inbox")
      await click("Lunch takes you about 1h")
      await has("Plan 1h from now on?", "div.fr-gutter")
      await click("Plan 1h")
      await has("Lunch is planned at 60 min from today")
      expect(await waitFor(async () => !(await meals(q)).changes.some((x) => x.kind === "lunch")), "still offered")
      await gone("Lunch takes you about 1h", "[role=list]")
      undo.push((await q("log_list", { limit: 5 })).find((e) => e.command === "meal_use_length").id)
    },
  },
  {
    name: "breakfasts at ten are asked about in the Inbox; its answer moves the routine there",
    async run({ open, click, has, q, c, day, expect }) {
      for (let n = 1; n <= 6; n++) undo.push((await c("meal_log", { kind: "breakfast", start: `${day(-n)}T10:30`, end: `${day(-n)}T10:50` })).command_id)
      const offer = await waitFor(async () => (await meals(q)).times.find((x) => x.kind === "breakfast"))
      expect(offer?.usual_start === "10:30", `what's learned: ${JSON.stringify(offer)}`)
      await open("/inbox")
      await click("You usually have breakfast around 10:30am")
      await has(`Plan it ${twelve(offer.new_start)}–${twelve(offer.new_end)} instead?`, "div.fr-gutter")
      await click(`Plan ${twelve(offer.new_start)}–${twelve(offer.new_end)}`)
      await has("Breakfast is planned")
      expect(await waitFor(async () => !(await meals(q)).times.some((x) => x.kind === "breakfast")), "still offered")
      undo.push((await q("log_list", { limit: 5 })).find((e) => e.command === "meal_use_time").id)
    },
  },
  {
    name: "the server refuses meals while it can't take them",
    async run({ request, day, expect }) {
      const post = (name, body) => request("POST", `/api/c/${name}`, body)
      const back = await post("meal_log", { kind: "lunch", start: `${day(-8)}T13:00`, end: `${day(-8)}T12:00` })
      expect(back.status === 422 && back.body.message.includes("a meal ends after it starts, within four hours"), JSON.stringify(back))
      const ahead = await post("meal_skip", { kind: "dinner", date: day(2) })
      expect(ahead.status === 422 && ahead.body.message.includes("that day hasn't come yet"), JSON.stringify(ahead))
      const end = await post("meal_end", {})
      expect(end.status === 422 && end.body.message.includes("you aren't eating"), JSON.stringify(end))
      for (const name of ["meal_edit", "meal_remove"]) {
        const none = await post(name, name === "meal_edit" ? { id: 999_999, start: `${day(-1)}T12:00` } : { id: 999_999 })
        expect(none.status === 422 && none.body.message.includes("no meal 999999"), `${name}: ${JSON.stringify(none)}`)
      }
      const nothing = await post("meal_use_length", { kind: "snack" })
      expect(nothing.status === 422 && nothing.body.field === "kind", JSON.stringify(nothing))
      const planned = await post("meal_plan", { kind: "lunch", plan: true })
      expect(planned.status === 422 && planned.body.message.includes("lunch is already planned"), JSON.stringify(planned))
    },
  },
  {
    name: "what was logged is undone and tracking put back as it was",
    async run({ q, c, expect }) {
      for (const id of undo.reverse()) if (id) await c("undo", { command_id: id })
      undo.length = 0
      if (tracking && !tracking.on) await c("settings_set", { key: "meal_tracking", value: tracking })
      expect((await q("settings")).meal_tracking.on === !!tracking?.on, "tracking isn't as it was")
    },
  },
]
