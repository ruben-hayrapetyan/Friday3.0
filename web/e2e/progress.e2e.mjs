// Work done (tests/features.toml: progress): Start on a block times it (start) and the Dock says so; the Dock's More →
// Stuck notes it (stuck); its Pause stops it (stop). On a to-do's page the done bar's keys set how much is done
// (progress) and Start over takes it back; Log time counts time worked without the timer (log), and that sitting,
// opened on the plan, changes when you worked (sitting_edit) or goes (sitting_delete). In the Inbox, a block nobody said
// anything about is answered (review_task). Checked on the page and on the server.

const MEALS = /^(Breakfast|Lunch|Dinner)$/
const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const item = async (q, id) => (await q("item", { id })).item
let task = null // a to-do of the sample's, worked on through these tests

export default [
  {
    name: "Start on a block times it and the Dock says so; More → Stuck notes it; Pause stops the timer",
    async run({ open, click, has, until, q, planned, evaluate, expect }) {
      await planned()
      await open("/")
      const plan = await q("plan")
      let b = null
      for (const x of plan.blocks) {
        if (x.pinned || x.fixed || x.background || MEALS.test(x.title) || new Date(x.start) < new Date(Date.now() + 3_600_000)) continue
        if (await evaluate(`!!document.querySelector('[data-block-key="${x.key}"]')`)) {
          b = x
          break
        }
      }
      expect(b, "no block of work coming up on the page")
      task = { id: b.item_id, title: b.title }
      expect(!(await q("status")).timer, "something is being timed already")
      await evaluate(`document.querySelector('[data-block-key="${b.key}"]').click()`)
      await has(b.title, ".fr-block-card")
      await click("Start|Resume")
      await settle(async () => (await q("status")).timer?.item_id === b.item_id, `${b.title} timed on the server`)
      await until(`[...document.querySelectorAll(".fr-block-card button")].some((x) => x.innerText.startsWith("Pause"))`, 10_000, "Pause on the card")
      await click("More")
      await click("Stuck")
      await settle(async () => (await q("log_list", { item_id: b.item_id, limit: 5 })).some((e) => e.command === "stuck"), "stuck noted on the server")
      await click("Pause the timer (Space)")
      await settle(async () => !(await q("status")).timer, "the timer stopped on the server")
      expect((await q("log_list", { limit: 5 })).some((e) => e.command === "stop"), "no stop in the history") // Pause stops whatever runs
    },
  },
  {
    name: "the done bar's keys set how much is done, and Start over takes it back",
    async run({ open, click, has, until, q, evaluate, expect }) {
      expect(task, "the test before found no task")
      const before = await item(q, task.id)
      const total = before.done_min + before.remaining_min
      await open(`/todo?item=${task.id}`)
      await has("Planned sessions")
      await evaluate(`document.querySelector('[role=slider][aria-label="How much is done"]').focus()`)
      await (await import("node:timers/promises")).setTimeout(100)
      await t_press(evaluate, "End")
      await settle(async () => (await item(q, task.id)).remaining_min === 0 || (await item(q, task.id)).done_min >= total, "all of it done on the server")
      await until(`document.querySelector('[role=slider][aria-label="How much is done"]')?.getAttribute("aria-valuenow") === "100"`, 10_000, "the bar full")
      await click("Start over")
      await settle(async () => (await item(q, task.id)).done_min === 0, "nothing done on the server")
      await until(`document.querySelector('[role=slider][aria-label="How much is done"]')?.getAttribute("aria-valuenow") === "0"`, 10_000, "the bar empty")
    },
  },
  {
    name: "Log time counts time worked without the timer",
    async run({ open, click, has, q, expect }) {
      expect(task, "the first test found no task")
      const before = await item(q, task.id)
      await open(`/todo?item=${task.id}`)
      await has("Planned sessions")
      await click("Log time")
      await has("Time you worked on it without the timer:")
      await click("Log it")
      await settle(async () => (await item(q, task.id)).done_min > before.done_min, "the time counted on the server")
      const logged = (await item(q, task.id)).done_min - before.done_min
      expect(logged >= 15, `only ${logged} min counted`)
      expect((await q("log_list", { item_id: task.id, limit: 3 }))[0].command === "log", "no log in its history")
      await has(`${Math.floor((before.done_min + logged) / 60) ? `${Math.floor((before.done_min + logged) / 60)}h` : ""}`)
    },
  },
  {
    name: "a timed sitting opened on the plan changes when you worked, and Remove takes its time away",
    async run({ open, click, type, has, until, q, folder, evaluate, expect }) {
      expect(task && folder, "this test needs the first test's task and the sample's folder")
      // an hour timed earlier today, as the timer records one (progress, source timer)
      const now = Date.now()
      const start = new Date(Math.floor((now - 5 * 3_600_000) / 300_000) * 300_000) // clear of the hour logged above
      const end = new Date(start.getTime() + 3_600_000)
      const utc = (d) => `${d.toISOString().slice(0, 16)}Z`
      const { DatabaseSync } = await import("node:sqlite")
      const db = new DatabaseSync(`${folder}/friday.db`)
      try {
        db.prepare("INSERT INTO progress (user_id, item_id, start_utc, end_utc, minutes, source, created_utc) VALUES (1, ?, ?, ?, 60, 'timer', ?)").run(task.id, utc(start), utc(end), utc(new Date(now))) // recorded now: after Start over above
      } finally {
        db.close()
      }
      const before = await item(q, task.id)
      const later = new Date(start.getTime() + 15 * 60_000)
      const local = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
      const shown = (at) => `!!document.querySelector('[data-block-key="S${task.id}@${local(at)}"]')`
      await open("/")
      await until(shown(start), 10_000, "the sitting on the calendar")
      await evaluate(`document.querySelector('[data-block-key="S${task.id}@${local(start)}"]').click()`)
      await has("Change when you worked", ".fr-block-card")
      await click("Change when you worked")
      await type("Started", `${String(later.getHours()).padStart(2, "0")}:${String(later.getMinutes()).padStart(2, "0")}`, { enter: true })
      await new Promise((r) => setTimeout(r, 300))
      if (await evaluate(`!!document.querySelector('[role=group][aria-label="When you worked"]')`)) await click("Save") // Enter set the time
      await settle(async () => (await item(q, task.id)).done_min === before.done_min - 15, `15 minutes fewer counted on the server (was ${before.done_min})`)
      await open("/")
      await until(shown(later), 10_000, "the sitting, changed, on the calendar")
      await evaluate(`document.querySelector('[data-block-key="S${task.id}@${local(later)}"]').click()`)
      await click("Remove this sitting")
      await settle(async () => (await item(q, task.id)).done_min === before.done_min - 60, "the sitting's time taken away on the server")
      await until(`!(${shown(later)})`, 10_000, "the sitting gone from the calendar")
    },
  },
  {
    name: "in the Inbox, a block nobody said anything about is answered, and leaves the Inbox",
    async run({ open, click, has, until, q, day, evaluate, expect }) {
      let date = null
      let gap = null
      for (const d of [day(-1), day(0), day(-2)]) {
        gap = ((await q("review", { date: d })).gaps ?? []).find((g) => !g.answer && g.planned_min >= 15)
        if (gap) {
          date = d
          break
        }
      }
      if (!gap) return console.log("      (no block waiting for an answer in the sample: nothing to answer)")
      await open("/inbox")
      await has(gap.title, "main")
      await evaluate(`(() => {
        const rows = [...document.querySelectorAll("main button, main [role=option]")].filter((b) => b.innerText.includes(${JSON.stringify(gap.title)}) && b.innerText.includes("did you do it?"))
        rows.sort((a, b) => a.innerText.length - b.innerText.length)[0]?.click()
      })()`)
      await has("how much did you do?", "main")
      await click("None")
      await settle(async () => ((await q("review", { date })).gaps ?? []).find((g) => g.item_id === gap.item_id)?.answer || !((await q("review", { date })).gaps ?? []).some((g) => g.item_id === gap.item_id), "the answer on the server")
      await until(`![...document.querySelectorAll("main button, main [role=option]")].some((b) => b.innerText.includes(${JSON.stringify(gap.title)}) && b.innerText.includes("did you do it?"))`, 10_000, "the question gone from the Inbox")
    },
  },
]

/** A key pressed on the focused element, as the keyboard sends it. */
const t_press = (evaluate, key) => evaluate(`document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: ${JSON.stringify(key)}, bubbles: true }))`)
