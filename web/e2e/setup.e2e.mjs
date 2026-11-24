// Setup (tests/features.toml: setup): the questions Friday asks when it first opens, then its tour, once. One answer
// changed alone from Settings → Change a Setup answer is saved (setup_save) and Cancel keeps it as it was; going
// through every question again changes nothing you didn't change; and a Friday opened for the first time asks Setup
// before anything else, "Skip: keep Friday's guesses" saves them, and the tour opens once (tour_offered), never again.
// Checked on the page and on the server.

import { DatabaseSync } from "node:sqlite"
import path from "node:path"

const answers = async (q) => (await q("setup")).answers
const settle = async (check, what) => {
  for (let i = 0; i < 60; i++, await new Promise((r) => setTimeout(r, 250))) if (await check()) return
  throw new Error(`waited 15s for ${what}`)
}
const dialogOpen = `!!document.querySelector(".wk-stage[role=dialog]")`

const openAnswer = async ({ open, click, has }, label, title) => {
  await open("/settings")
  await click("Change a Setup answer")
  await click(label)
  await has(title, "body", 15_000)
}

export default [
  {
    name: "one answer changed alone is saved, and the rule it's about follows",
    async run(t) {
      const { click, until, q, expect } = t
      const before = await answers(q)
      const days = before.finish_early_days === 2 ? 3 : 2
      await openAnswer(t, "How early work is done", "early")
      await click(days === 2 ? "2 days early" : "3 days early")
      await click("Save")
      await until(`!${dialogOpen}`, 10_000, "Setup closed after Save")
      await settle(async () => (await answers(q)).finish_early_days === days, `finishing ${days} days early on the server`)
      const after = await answers(q)
      expect(after.wake === before.wake && after.normal_hours === before.normal_hours, "changing one answer changed others")
      const rule = (await q("rules")).find((r) => r.name === "finish_early")
      expect(rule.sentence.includes(`${days} days`), `the rule says "${rule.sentence}", not ${days} days`)
    },
  },
  {
    name: "Cancel leaves the answer as it was",
    async run(t) {
      const { click, until, q, expect } = t
      const before = (await answers(q)).finish_early_days
      await openAnswer(t, "How early work is done", "early")
      await click("On the day")
      await click("Cancel")
      await until(`!${dialogOpen}`, 10_000, "Setup closed after Cancel")
      await new Promise((r) => setTimeout(r, 1000))
      expect((await answers(q)).finish_early_days === before, "Cancel saved the answer")
    },
  },
  {
    name: "going through every question again, changing nothing, leaves every setting as it was",
    async run({ open, click, until, evaluate, q, expect }) {
      const settings = async () => {
        const s = await q("settings")
        return JSON.stringify([s.sleep, s.rules, s.time?.day_start])
      }
      const before = await settings()
      await open("/settings")
      await click("Change a Setup answer")
      await click("All of Setup’s questions, in order")
      await until(dialogOpen, 10_000, "Setup open")
      await until(`document.body.innerText.includes("Fit Friday to your week again.")`, 15_000, "Setup's first question, said as done before")
      let steps = 0
      for (; steps < 40 && (await evaluate(dialogOpen)); steps++) {
        await until(`(() => { const b = document.querySelector(".wk-go"); return !!b && !b.disabled })() || !${dialogOpen}`, 15_000, "the next stop")
        await evaluate(`document.querySelector(".wk-go")?.click()`)
        await new Promise((r) => setTimeout(r, 400))
      }
      expect(!(await evaluate(dialogOpen)), `Setup still open after ${steps} stops`)
      expect(steps >= 5, `Setup had only ${steps} stops`)
      await new Promise((r) => setTimeout(r, 1000))
      expect((await settings()) === before, "going through Setup again changed settings nobody changed")
      expect((await q("setup")).done, "Setup isn't done")
    },
  },
  {
    name: "a first opening asks Setup first; Skip keeps Friday's guesses, then the tour opens once and not again",
    async run({ open, click, has, until, evaluate, q, folder, expect }) {
      expect(folder, "this test needs the sample's folder (run without --url, or give --folder)")
      const db = new DatabaseSync(path.join(folder, "friday.db"))
      try {
        db.exec("UPDATE kv SET value = 'false' WHERE key IN ('setup_done', 'tour_offered')")
      } finally {
        db.close()
      }
      const before = await q("setup")
      expect(!before.done && !before.toured, "the sample still says Setup was done")
      await open("/")
      await until(dialogOpen, 15_000, "Setup opening by itself")
      await has("Skip: keep Friday's guesses", "body", 15_000)
      await click("Skip: keep Friday's guesses")
      await settle(async () => (await q("setup")).done, "Setup done on the server")
      await until(`!!document.querySelector('[role=dialog][aria-label^="Tour of Friday"]')`, 15_000, "the tour opening")
      await settle(async () => (await q("setup")).toured, "the tour said offered on the server")
      await click("End the tour")
      await until(`!document.querySelector('[role=dialog][aria-label^="Tour of Friday"]')`, 10_000, "the tour closed")
      await open("/")
      await new Promise((r) => setTimeout(r, 2500)) // the tour waits 900 ms before opening by itself
      expect(!(await evaluate(`!!document.querySelector('[role=dialog][aria-label^="Tour of Friday"]')`)), "the tour opened again")
      expect(!(await evaluate(dialogOpen)), "Setup opened again once done")
    },
  },
]
