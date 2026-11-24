// Rules (tests/features.toml: rules), the Rules page: a rule typed as you'd say it is read back before it's added
// (rule_read), added (rule_add) and listed with your words; its strength, its switch, its words (rule_edit) and its
// deletion change it on the server; two rules that can't both be kept say so on their rows, and choosing the one
// that wins is kept (rule_win); words Friday can't read are said so, with the AI offered. Checked on the page and
// against the server's rules.

const rules = async (q) => await q("rules")
const mine = async (q, sentence) => (await rules(q)).find((r) => r.sentence === sentence)
const settle = async (check, what) => {
  for (let i = 0; i < 60; i++, await new Promise((r) => setTimeout(r, 250))) if (await check()) return
  throw new Error(`waited 15s for ${what}`)
}
/** Presses the button named `name` inside the rule's own row. */
const inRow = (evaluate, rule, name) =>
  evaluate(`(() => {
    const row = document.querySelector('[data-rule="${rule}"]')
    const b = row && [...row.querySelectorAll("button")].find((b) => (b.getAttribute("aria-label") || b.textContent).trim() === ${JSON.stringify(name)})
    if (!b) return false
    b.click()
    return true
  })()`)

const LUNCH = "Lunch before 1pm"

export default [
  {
    name: "a rule typed as you'd say it is read back before it's added, then listed with your words",
    async run({ open, type, click, has, q, expect }) {
      await open("/rules")
      await type("New rule", "I prefer eating lunch before 1pm")
      await has("Friday read this as")
      await has(LUNCH)
      expect(!(await mine(q, LUNCH)), "the rule was added before Add rule")
      await click("Add rule")
      await settle(async () => !!(await mine(q, LUNCH)), "the rule on the server")
      const rule = await mine(q, LUNCH)
      expect(rule.source === "you" && rule.enabled && rule.strength === "Prefer", `added as ${JSON.stringify(rule)}`)
      expect(rule.words === "I prefer eating lunch before 1pm", `its words kept as ${rule.words}`)
      await has("You wrote: “I prefer eating lunch before 1pm”")
    },
  },
  {
    name: "its strength and its switch change it on the server and on its row",
    async run({ open, has, until, q, evaluate, expect }) {
      const rule = await mine(q, LUNCH)
      await open("/rules")
      await has(LUNCH)
      expect(await inRow(evaluate, rule.name, "Strongly"), "no Strongly on its row")
      await settle(async () => (await mine(q, LUNCH)).strength === "Strongly", "Strongly on the server")
      await until(`document.querySelector('[data-rule="${rule.name}"] [aria-pressed=true]')?.textContent === "Strongly"`, 10_000, "Strongly chosen on its row")
      expect(await inRow(evaluate, rule.name, `Switch off ${LUNCH}`), "no switch on its row")
      await settle(async () => (await mine(q, LUNCH)).enabled === false, "switched off on the server")
      await until(`document.querySelector('[data-rule="${rule.name}"] [role=switch]')?.getAttribute("aria-checked") === "false"`, 10_000, "its switch off")
      expect(await inRow(evaluate, rule.name, `Switch on ${LUNCH}`), "no switch to turn it on again")
      await settle(async () => (await mine(q, LUNCH)).enabled === true, "switched on again on the server")
    },
  },
  {
    name: "Edit rule changes its words and Friday's reading, and it stays one rule",
    async run({ open, type, click, has, q, evaluate, expect }) {
      const rule = await mine(q, LUNCH)
      const count = (await rules(q)).length
      await open("/rules")
      await has(LUNCH)
      expect(await inRow(evaluate, rule.name, "Edit rule"), "no Edit rule on its row")
      await has("Editing “Lunch before 1pm”")
      await type("Rule", "I prefer eating lunch before 12pm")
      await has("Lunch before 12pm")
      await click("Save")
      await settle(async () => !!(await mine(q, "Lunch before 12pm")), "the edited rule on the server")
      expect(!(await mine(q, LUNCH)), "the old words are still a rule")
      expect((await rules(q)).length === count, "editing made another rule")
      const edited = await mine(q, "Lunch before 12pm")
      expect(edited.reading.at === "12:00" && edited.words === "I prefer eating lunch before 12pm", `read as ${JSON.stringify(edited.reading)}`)
    },
  },
  {
    name: "two rules that can't both be kept say so; the one chosen wins over the other",
    async run({ open, type, click, has, q, evaluate, expect }) {
      await open("/rules")
      await type("New rule", "I prefer eating lunch after 2pm")
      await has("Lunch after 2pm")
      await click("Add rule")
      await settle(async () => !!(await mine(q, "Lunch after 2pm")), "the second rule on the server")
      const early = await mine(q, "Lunch before 12pm")
      const late = await mine(q, "Lunch after 2pm")
      const said = [...(early.contradicts ?? []), ...(late.contradicts ?? [])]
      expect(said.length > 0, `the server finds no contradiction: ${JSON.stringify([early.contradicts, late.contradicts])}`)
      await open("/rules")
      await has("Contradicts")
      await has("Which should win?")
      // the row that says so offers both; the earlier lunch is chosen
      const row = (early.contradicts ?? []).length ? early.name : late.name
      expect(await inRow(evaluate, row, "Lunch before 12pm"), "no button to let the earlier lunch win")
      await settle(async () => ((await mine(q, "Lunch before 12pm")).wins_over ?? []).includes(late.name), "the earlier lunch winning on the server")
      expect(((await mine(q, "Lunch after 2pm")).gives_way_to ?? []).includes(early.name), "the later lunch doesn't give way")
      await open("/rules")
      await has("Wins over “Lunch after 2pm”")
      await has("Gives way to “Lunch before 12pm”")
    },
  },
  {
    name: "Delete rule takes each away from the page and the server",
    async run({ open, has, until, q, evaluate, expect }) {
      await open("/rules")
      for (const sentence of ["Lunch after 2pm", "Lunch before 12pm"]) {
        const rule = await mine(q, sentence)
        await has(sentence)
        expect(await inRow(evaluate, rule.name, "Delete rule"), `no Delete rule on ${sentence}`)
        await settle(async () => !(await mine(q, sentence)), `${sentence} gone from the server`)
        await until(`!document.querySelector('[data-rule="${rule.name}"]')`, 10_000, `${sentence} gone from the page`)
      }
    },
  },
  {
    name: "words Friday can't read are said so, with the AI offered, and nothing is added",
    async run({ open, type, has, until, q, expect }) {
      const count = (await rules(q)).length
      await open("/rules")
      await type("New rule", "zorp the flimbles quarterly")
      await has("Friday can’t read this one itself.")
      await until(`[...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Ask Claude" && !b.disabled)`, 10_000, "an Ask Claude button")
      expect((await rules(q)).length === count, "unreadable words added a rule")
    },
  },
]
