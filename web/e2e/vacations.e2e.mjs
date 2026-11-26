// Breaks (tests/features.toml: vacations): Settings → Breaks → Add a break, named, its days chosen and Off, is added
// (vacation_add) and its days are break days on the calendar; opened again, its meals switch and its name change it
// as you go (vacation_edit); Delete break takes it away (vacation_delete). A Light break from today shows on the
// plan as a list for the day (vacation_day), and ticking a thing on it counts it (vacation_tick). Checked on the page
// and on the server.

const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const named = async (q, name) => (await q("vacations")).vacations.find((v) => v.name === name)
/** A date field set as a person picks a day: its value, then the events a date picker sends. */
const setDate = (evaluate, label, value) =>
  evaluate(`(() => {
    const el = document.querySelector('input[aria-label="${label}"]')
    if (!el) return false
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, "${value}")
    el.dispatchEvent(new Event("input", { bubbles: true }))
    el.dispatchEvent(new Event("change", { bubbles: true }))
    return true
  })()`)
const breakDay = async (q, date) => (await q("calendar", { start: date, days: 1 })).days[0].vacation

export default [
  {
    name: "Add a break, named, on chosen days and Off, is added and its days are break days",
    async run({ open, click, type, has, until, q, evaluate, day, expect }) {
      const [first, last] = [day(8), day(9)]
      expect(!(await breakDay(q, first)), "the day is a break day already")
      await open("/settings/breaks")
      await click("Add a break")
      await has("A new break")
      await type("Name", "E2E trip")
      await evaluate(`[...document.querySelectorAll("[role=dialog] button.fr-well")][0]?.click()`) // the Days row
      await until(`!!document.querySelector('input[aria-label="First day"]')`, 10_000, "the day pickers")
      expect(await setDate(evaluate, "First day", first), "no First day field")
      expect(await setDate(evaluate, "Last day", last), "no Last day field")
      await has("2 days")
      await click("Work during the break") // Friday's own menu (25 Nov: it opened a panel the dialog's width)
      await click("Off")
      await click("Add break")
      await settle(async () => !!(await named(q, "E2E trip")), "the break on the server")
      const v = await named(q, "E2E trip")
      expect(v.start === first && v.end === last && v.mode === "off", `added as ${JSON.stringify(v)}`)
      await has("E2E trip")
      const said = await breakDay(q, first)
      expect(said && said.name === "E2E trip", `the calendar's ${first} isn't the break: ${JSON.stringify(said)}`)
      expect(!(await breakDay(q, day(10))), "the day after the break is a break day")
    },
  },
  {
    name: "a break opened again changes as you go: its meals switch and its name",
    async run({ open, click, type, has, until, q, press, expect }) {
      const v = await named(q, "E2E trip")
      await open("/settings/breaks")
      await click("E2E trip")
      await has("Changes are saved as you make them.")
      await click("Plan meals during the break")
      await settle(async () => (await named(q, "E2E trip"))?.plan_meals === !v.plan_meals, "meals switched on the server")
      await type("Name", "E2E trip away", { enter: true })
      await settle(async () => !!(await named(q, "E2E trip away")), "the new name on the server")
      expect((await named(q, "E2E trip away")).id === v.id, "renaming made another break")
      await click("Done")
      await until(`!document.body.innerText.includes("Changes are saved as you make them.")`, 10_000, "the break closed")
      await has("E2E trip away")
    },
  },
  {
    name: "Delete break takes it off the page, the server and the calendar",
    async run({ open, click, has, until, q, day, expect }) {
      await open("/settings/breaks")
      await click("E2E trip away")
      await click("Delete break")
      await settle(async () => !(await named(q, "E2E trip away")), "the break gone from the server")
      await until(`!document.body.innerText.includes("E2E trip away")`, 10_000, "the break gone from the page")
      expect(!(await breakDay(q, day(8))), "its day is still a break day")
    },
  },
  {
    name: "a Light break from today is a list on the plan; ticking a thing counts it, unticking takes it back",
    async run({ open, click, has, until, q, c, planned, evaluate, day, expect }) {
      const today = day(0)
      const made = await c("vacation_add", { name: "E2E light days", start: today, end: day(1), mode: "light", work_min: 120 })
      try {
        await planned()
        const list = await settle(async () => (await q("vacation_day", { date: today })).items?.length > 0, "the day's list on the server", 60_000).then(() => q("vacation_day", { date: today }))
        const thing = list.items.find((t) => !t.ticked && !t.done)
        expect(thing, `nothing to tick on today's list: ${JSON.stringify(list.items)}`)
        await open("/")
        await has("E2E light days")
        await evaluate(`[...document.querySelectorAll(".fr-break-line")][0]?.click()`)
        await has(thing.title)
        const tick = (label) =>
          evaluate(`(() => {
            const row = [...document.querySelectorAll(".fr-hover")].find((r) => r.innerText.includes(${JSON.stringify(thing.title)}) && r.querySelector('[role=checkbox]'))
            const b = row?.querySelector('[role=checkbox][aria-label="${label}"]')
            if (!b) return false
            b.click()
            return true
          })()`)
        expect(await tick("Mark done"), `no Mark done beside ${thing.title}`)
        await settle(async () => (await q("vacation_day", { date: today })).items.find((t) => t.item_id === thing.item_id)?.ticked, "ticked on the server")
        await until(`document.body.innerText.includes("1/")`, 10_000, "the day's count going up")
        expect(await tick("Mark not done"), "no Mark not done once ticked")
        await settle(async () => !(await q("vacation_day", { date: today })).items.find((t) => t.item_id === thing.item_id)?.ticked, "unticked on the server")
      } finally {
        await c("vacation_delete", { id: made.result.id ?? (await named(q, "E2E light days")).id })
      }
      expect(!(await named(q, "E2E light days")), "the light break wasn't deleted")
    },
  },
]
