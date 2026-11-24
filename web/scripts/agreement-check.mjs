#!/usr/bin/env node
// Does Friday agree with itself? Opens Friday's pages in headless Chrome and checks that each number and sentence
// matches the plan and every other place that says the same thing (23 Nov: "there are a lot of inconsistencies in
// the text/stats that friday tells the user which is a persistent issue"). The plan is the one source of truth: the
// server's own answers (/api/q/plan, status, items, projects …) are read beside each page.
//
// It serves Alex's lived-in sample (`fridayd demo --case alex --ready`), then makes the weeks that bring out
// disagreements, which the sample alone doesn't have: hard work that can't all fit before it's due (late work and an
// overfull day), a project whose steps wait for each other, and soft work past its due. Each check says what one place
// says, what the other says, and where.
//
//   node web/scripts/agreement-check.mjs [--url http://127.0.0.1:8791] [--only late] [--case alex]
//
// Exit 0: everything agrees. Exit 1: something disagrees (listed). Exit 2: it couldn't run. Build web/dist first.

import { SETTLE, evaluate, go, openChrome, press, serveSample, wait } from "./browser.mjs"

const args = process.argv.slice(2)
const option = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
const only = option("--only")

// ---- the server's answers -------------------------------------------------------------------------------------------

function server(base) {
  const q = async (name, params = {}) => {
    const r = await fetch(`${base}/api/q/${name}?${new URLSearchParams(params)}`)
    if (!r.ok) throw new Error(`${name}: ${r.status} ${(await r.text()).slice(0, 200)}`)
    return r.json()
  }
  const c = async (name, body) => {
    const r = await fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
    const said = await r.json()
    if (!r.ok || said.ok === false) throw new Error(`${name}: ${r.status} ${JSON.stringify(said).slice(0, 300)}`)
    return said
  }
  /** Until the plan answers for the latest change (no plan still being worked out). */
  const planned = async () => {
    for (let until = Date.now() + 180_000; Date.now() < until; await wait(400)) {
      const s = await q("status")
      if (s.plan_generation !== null && s.plan_generation >= s.generation) {
        const p = await q("plan", { start: day(0) + "T00:00", end: day(1) + "T00:00" })
        if (!p.provisional) return
      }
    }
    throw new Error("the plan wasn't made within three minutes")
  }
  return { q, c, planned }
}

/** A local date `n` days from today, as the pages write it. */
function day(n) {
  const d = new Date(Date.now() + n * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
const localNow = () => {
  const d = new Date()
  return `${day(0)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

// ---- the weeks that bring disagreements out --------------------------------------------------------------------------

async function makeWeeks({ c, planned }) {
  // Hard work due tomorrow morning, more than the evening and night leave room for: some of it will be late, and
  // today and tomorrow fill past their usual hours.
  for (const [title, hours] of [["Agreement: lab report", 6], ["Agreement: problem set", 5], ["Agreement: essay draft", 7]])
    await c("add", { title, preset: "Assignment", due: `${day(1)}T09:00`, duration_min: hours * 60, firmness: "hard" })
  // A project whose steps wait for each other, the last with little room.
  const project = (await c("add", { title: "Agreement: robotics demo", preset: "Project", due: `${day(4)}T17:00`, firmness: "hard" })).result.item.id
  const steps = []
  for (const [title, minutes] of [["Design the arm", 300], ["Build the arm", 600], ["Rehearse the demo", 120]])
    steps.push((await c("add", { title, parent_id: project, duration_min: minutes })).result.item.id)
  await c("depend", { item_id: steps[1], depends_on_id: steps[0] })
  await c("depend", { item_id: steps[2], depends_on_id: steps[1] })
  // Soft work already past its due.
  await c("add", { title: "Agreement: reading response", preset: "Reading", due: `${day(-1)}T17:00`, duration_min: 90, firmness: "soft" })
  // Sleep tracked, four nights logged: 8h, 6h, 7h15 and 5h30, the last ending yesterday morning (so none is in the
  // future, whatever the hour the check runs).
  await c("settings_set", { key: "sleep_tracking", value: { on: true } })
  for (const [n, bed, up] of [[5, "23:30", "07:30"], [4, "00:30", "06:30"], [3, "23:30", "06:45"], [2, "01:00", "06:30"]]) {
    await c("sleep_mark", { kind: "bed", at: `${bed < "12:00" ? day(1 - n) : day(-n)}T${bed}` })
    await c("sleep_mark", { kind: "up", at: `${day(1 - n)}T${up}` })
  }
  await planned()
}

// ---- reading a page --------------------------------------------------------------------------------------------------

const text = (page, selector = "body") => evaluate(page, `(document.querySelector(${JSON.stringify(selector)})?.innerText ?? "").replace(/\\s+/g, " ")`)

/** Each element matching `selector`: its attribute `attr` and its text. */
const each = (page, selector, attr) =>
  evaluate(page, `[...document.querySelectorAll(${JSON.stringify(selector)})].map((el) => ({ key: el.getAttribute(${JSON.stringify(attr)}), text: el.innerText.replace(/\\s+/g, " "), next: el.querySelector('[title="Next planned"]')?.innerText ?? null }))`)

// ---- the checks ------------------------------------------------------------------------------------------------------
// Each: a name, and a function given the server, the page and `go(route)` that returns what disagrees, each as
// { where, says, but }.

const lateTitle = (late) => (late.length === 1 ? `${late[0].title} will be late` : `${late.length} things will be late`)
const futureBlocks = (plan, id) => plan.blocks.filter((b) => b.item_id === id && b.end > localNow() && !b.state)

const CHECKS = [
  {
    name: "late: the Plan page's note says what the plan has late",
    async run({ q, open, page }) {
      const late = (await q("status")).late_items ?? []
      await open("/")
      const body = await text(page)
      if (!late.length) return body.includes("will be late") ? [{ where: "Plan page", says: "something will be late", but: "the plan has nothing late" }] : []
      return body.includes(lateTitle(late)) ? [] : [{ where: "Plan page", says: `no "${lateTitle(late)}"`, but: `the plan has ${late.length} late: ${late.map((l) => l.title).join(", ")}` }]
    },
  },
  {
    name: "late: the Inbox counts the late work the Plan page does",
    async run({ q, open, page }) {
      const late = (await q("status")).late_items ?? []
      await open("/inbox")
      const body = await text(page)
      const said = body.match(/(\d+) things will be late/)?.[1] ?? (body.match(/([^.:]+?) will be late/) ? "1" : null)
      if (!late.length && !said) return []
      if (String(late.length) === said) return []
      return [{ where: "Inbox", says: said ? `${said} will be late` : "nothing about late work", but: `the Plan page says "${lateTitle(late)}"` }]
    },
  },
  {
    name: "late: See options (Triage) lists the same late work",
    async run({ q }) {
      const late = (await q("status")).late_items ?? []
      const triage = await q("triage")
      const there = Array.isArray(triage.late) ? triage.late.map((l) => l.title ?? l) : Object.keys(triage.late ?? {})
      const want = late.map((l) => l.title).sort()
      const got = [...there].sort()
      return JSON.stringify(want) === JSON.stringify(got) ? [] : [{ where: "Triage", says: got.length ? `late now: ${got.join(", ")}` : "Nothing is going late.", but: `the Plan page's late work: ${want.join(", ") || "none"}` }]
    },
  },
  {
    name: "late: a late item's block doesn't say it's on time",
    async run({ q }) {
      const late = (await q("status")).late_items ?? []
      const plan = await q("plan", { start: `${day(-1)}T00:00`, end: `${day(14)}T00:00` })
      const found = []
      for (const l of late)
        for (const b of futureBlocks(plan, l.item_id)) {
          const why = JSON.stringify(await q("why", { key: b.key }))
          if (/no room to spare|on time|in time/i.test(why)) found.push({ where: `${l.title}'s block ${b.start}, Why`, says: why.match(/[^"]*(no room to spare|on time|in time)[^"]*/i)?.[0], but: `it's ${l.hours} h late` })
        }
      return found
    },
  },
  {
    name: "overload: a day's \"h over\" matches its planned hours and usual hours",
    async run({ q, open, page }) {
      await open("/")
      await press(page, "w")
      await evaluate(page, SETTLE)
      // the week's day headers (the small month beside it marks its days the same way: those are left out)
      const seen = new Set()
      const shown = (await each(page, "[data-drop-day]", "data-drop-day")).filter((s) => /^\d{1,2} [A-Z][a-z]{2}/.test(s.text) && !seen.has(s.key) && seen.add(s.key))
      const dates = shown.map((s) => s.key).filter(Boolean)
      if (!dates.length) return [{ where: "Plan week", says: "no days", but: "a week shows seven" }]
      const plan = await q("plan", { start: `${dates[0]}T00:00`, end: `${day(30)}T00:00` })
      const cal = await q("calendar", { start: dates[0], days: dates.length })
      const found = []
      for (const s of shown) {
        const cap = cal.days.find((d) => d.date === s.key)?.cap_hours
        const hours = plan.day_hours[s.key] ?? 0
        const over = cap == null ? 0 : hours - cap
        const says = Number(s.text.match(/([\d.]+) h over/)?.[1] ?? 0)
        if ((over > 0.05) !== (says > 0) || (says > 0 && Math.abs(says - over) > 0.1))
          found.push({ where: `Plan week, ${s.key}`, says: says ? `${says} h over` : "not over", but: `the plan has ${hours} h that day against ${cap} h usual${over > 0 ? `: ${over.toFixed(1)} h over` : ""}` })
      }
      return found
    },
  },
  {
    name: "to-do: a row's planned time and its tag agree",
    async run({ q, open, page }) {
      const status = await q("status")
      await open("/todo")
      const rows = await each(page, "[data-todo-row]", "data-todo-row")
      const found = []
      for (const r of rows) {
        const id = Number(r.key)
        const slip = status.slipping?.find((s) => s.item_id === id)
        const late = status.late_items?.find((s) => s.item_id === id)
        const time = r.next && !["—", "done", "·"].includes(r.next.trim()) ? r.next.trim() : null
        if (/not planned/.test(r.text) && time) found.push({ where: `To-do row ${id}`, says: `"not planned" and "${time}"`, but: "one of them is wrong" })
        if (late && !/late/.test(r.text)) found.push({ where: `To-do row ${id}`, says: "no late tag", but: `the plan has it ${late.hours} h late` })
        if (slip?.planned === false && time) found.push({ where: `To-do row ${id}`, says: `planned ${time}`, but: "status says it isn't planned before its due" })
      }
      return found
    },
  },
  {
    name: "to-do: the header counts the rows below it",
    async run({ q, open, page }) {
      await open("/todo")
      const head = await text(page, ".fr-page-head")
      const said = Number(head.match(/(\d+) open/)?.[1] ?? NaN)
      const open_ = new Set((await q("items", { status: "todo" })).map((i) => i.id))
      const rows = (await each(page, "[data-todo-row]", "data-todo-row")).filter((r) => open_.has(Number(r.key)))
      return said === rows.length ? [] : [{ where: "To-do header", says: `${said} open`, but: `the list below shows ${rows.length} open rows` }]
    },
  },
  {
    name: "to-do: an item's planned sessions are still to come",
    async run({ q, open, page }) {
      const items = (await q("items", { status: "todo" })).filter((i) => i.title.startsWith("Agreement") || i.parent_id)
      const found = []
      for (const item of items.slice(0, 8)) {
        const detail = await q("item", { id: item.id })
        const past = detail.blocks.filter((b) => b.end <= localNow() && !b.state)
        if (past.length) found.push({ where: `${item.title}, Planned sessions`, says: `${past.length} session(s) already over shown as "Planned · Friday decides" (${past[0].start})`, but: "they're past" })
        if (!detail.blocks.length && item.due && (item.duration_min ?? item.remaining_min)) {
          await open(`/todo?item=${item.id}`)
          const body = await text(page)
          if (body.includes("Friday will find time once it has a due date or an estimate"))
            found.push({ where: `${item.title}, Planned sessions`, says: "Friday will find time once it has a due date or an estimate", but: `it has both (due ${item.due}, ${item.duration_min ?? item.remaining_min} min)` })
        }
      }
      return found
    },
  },
  {
    name: "projects: a project's status agrees with its steps",
    async run({ q }) {
      const status = await q("status")
      const plan = await q("plan", { start: `${day(-1)}T00:00`, end: `${day(40)}T00:00` })
      const found = []
      for (const p of await q("projects")) {
        const steps = (p.steps ?? p.children ?? []).map((s) => s.item?.id ?? s.id)
        const late = (status.late_items ?? []).filter((l) => steps.includes(l.item_id) || l.item_id === p.item.id)
        const anyPlanned = steps.some((id) => futureBlocks(plan, id).length)
        if (late.length && ["on_track", "on track"].includes(p.status))
          found.push({ where: `Projects, ${p.item.title}`, says: "On track", but: `${late.map((l) => l.title).join(", ")} will be late` })
        if (p.status === "unplanned" && anyPlanned && !late.length)
          found.push({ where: `Projects, ${p.item.title}`, says: "Not planned yet", but: "its steps have time planned" })
      }
      return found
    },
  },
  {
    name: "sleep: a night is yellow when, and only when, it's an hour or more under your usual night",
    async run({ q, open, page }) {
      const sleep = await q("sleep")
      const usual = sleep.usual_night_min
      await open("/insights?tab=sleep")
      const cells = await evaluate(page, `[...document.querySelectorAll("span.tnum")].filter((s) => !s.closest("[data-tour=now]") && /^(\\d+h)?( ?\\d+m)?$/.test(s.innerText.trim()) && s.innerText.trim()).map((s) => ({ text: s.innerText.trim(), yellow: s.style.color.includes("warn") }))`)
      const found = []
      let compared = 0
      for (const n of sleep.nights.filter((n) => n.slept_min)) {
        const want = n.slept_min <= usual - 60
        const h = Math.floor(n.slept_min / 60), m = n.slept_min % 60
        const text = h ? `${h}h${m ? ` ${m}m` : ""}` : `${m}m`
        for (const cell of cells.filter((c) => c.text === text))
          if (++compared && cell.yellow !== want) found.push({ where: `Sleep, ${n.date}`, says: `${text} ${cell.yellow ? "yellow" : "gray"}`, but: `your usual night is ${usual / 60} h: it should be ${want ? "yellow" : "gray"}` })
      }
      if (process.env.AGREEMENT_PROGRESS) console.error(`  sleep: ${compared} cells compared`)
      return compared ? found : [{ where: "Sleep", says: "no night's hours on the page", but: `${sleep.nights.filter((n) => n.slept_min).length} nights were logged` }]
    },
  },
  {
    name: "now: the Now bar's free time ends where its length does",
    async run({ q, open, page }) {
      const now = await q("now")
      if (now.current || !now.gap_minutes) return []
      await open("/")
      const bar = await text(page, "[data-tour=now]")
      const h = Math.floor(now.gap_minutes / 60), m = now.gap_minutes % 60
      const length = h ? `${h}h${m ? ` ${m}m` : ""}` : `${m}m`
      const end = new Date(Date.now() + now.gap_minutes * 60_000)
      const found = []
      if (now.free_until && Math.abs(new Date(now.free_until).getTime() - end.getTime()) > 120_000)
        found.push({ where: "Now bar (server)", says: `free until ${now.free_until}`, but: `its ${length} end at ${end.toTimeString().slice(0, 5)}` })
      if (!bar.includes(length)) found.push({ where: "Now bar", says: bar.slice(0, 80), but: `the free time is ${length}` })
      return found
    },
  },
  {
    name: "breaks: a break day's counts agree on its panel, its calendar line and the Now bar",
    async run({ q, c, open, page, planned }) {
      // Friday's today, its planning day: after midnight and before your day starts it's still yesterday
      const today = (await q("calendar", { start: day(0), days: 1 })).today
      const made = (await c("vacation_add", { name: "Agreement break", start: today, end: day(2), mode: "light" })).result.vacation.id
      try {
        await planned()
        let list = await q("vacation_day", { date: today })
        if (list.items.length) await c("vacation_tick", { date: today, item_id: list.items[0].item_id, ticked: true })
        list = await q("vacation_day", { date: today })
        const left = list.items.filter((t) => !t.ticked).length
        const cal = (await q("calendar", { start: today, days: 1 })).days[0].vacation
        const found = []
        if ((cal.things ?? 0) - (cal.ticked ?? 0) !== left)
          found.push({ where: "the calendar's break line", says: `${(cal.things ?? 0) - (cal.ticked ?? 0)} to do`, but: `the day's list has ${left} left` })
        await open("/")
        const bar = await text(page, "[data-tour=now]")
        const want = !list.items.length ? "nothing to do today" : left ? `${left} thing${left === 1 ? "" : "s"} to do today` : "today's list is done"
        if (!bar.includes(want)) found.push({ where: "Now bar", says: bar.match(/[^.]*(to do today|list is done|nothing to do today)/)?.[0] ?? "no break line", but: `the day's list: ${want}` })
        return found
      } finally {
        await c("vacation_delete", { id: made })
        await planned()
      }
    },
  },
  {
    name: "insights: the counts add up",
    async run({ q }) {
      const i = await q("insights", { weeks: 4 })
      const kinds = (i.by_kind ?? []).reduce((s, k) => s + k.n, 0)
      return kinds > i.done ? [{ where: "Insights", says: `${i.done} things finished`, but: `the kinds below add up to ${kinds}` }] : []
    },
  },
  {
    name: "weekly review: the headline adds up its rows",
    async run({ q }) {
      const w = await q("week_review")
      const sum = (rows, f) => rows.reduce((s, r) => s + (r[f] ?? 0), 0)
      const found = []
      for (const f of ["planned_h", "actual_h"]) {
        const head = sum(w.areas ?? [], f)
        const rows = sum(w.groups ?? [], f)
        if (Math.abs(head - rows) > 0.15) found.push({ where: "Weekly review", says: `${head.toFixed(1)} h ${f === "planned_h" ? "planned" : "worked"} in the headline`, but: `the rows add up to ${rows.toFixed(1)} h` })
      }
      return found
    },
  },
]

// ---- running ---------------------------------------------------------------------------------------------------------

async function main() {
  const started = Date.now()
  const given = option("--url")
  const sample = given ? { base: given.replace(/\/$/, ""), stop: () => {} } : await serveSample({ case: option("--case") ?? "alex", prefix: "friday-agreement-" })
  const api = server(sample.base)
  const { page, close } = await openChrome()
  const findings = []
  const problems = []
  try {
    await page("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
    await api.planned()
    if (!given) await makeWeeks(api)
    const open = (route) => go(page, sample.base, route)
    for (const check of CHECKS) {
      if (only && !check.name.includes(only)) continue
      try {
        for (const f of await check.run({ ...api, page, open })) findings.push({ check: check.name, ...f })
      } catch (error) {
        problems.push(`${check.name}: ${error.message}`)
      }
      if (process.env.AGREEMENT_PROGRESS) console.error(`${check.name}: done`)
    }
  } finally {
    close()
    sample.stop()
  }
  for (const f of findings) console.log(`${f.check}\n  ${f.where} says: ${f.says}\n  but ${f.but}`)
  for (const p of problems) console.log(`couldn't check: ${p}`)
  const seconds = Math.round((Date.now() - started) / 1000)
  console.log(`${findings.length} disagreement${findings.length === 1 ? "" : "s"}, ${problems.length} check${problems.length === 1 ? "" : "s"} not run, in ${seconds}s`)
  process.exit(findings.length || problems.length ? 1 : 0)
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(130))

main().catch((error) => {
  console.error(error)
  process.exit(2)
})
