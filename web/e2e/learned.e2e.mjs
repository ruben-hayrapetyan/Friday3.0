// The learned lengths switch (tests/features.toml: learned), on Insights → Trends: Adjust new estimates automatically
// turns Friday's learned lengths on and off; the server keeps it and the page says what's in use, in the switch's
// line and under What Friday learned → So far. The sample has learned lengths, not yet in use.

const durations = async (q) => (await q("learning")).durations
const waitFor = async (check, ms = 10_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const switchOn = `document.querySelector("[aria-label='Adjust estimates']")?.getAttribute("aria-checked")`
let was

export default [
  {
    name: "on: Friday's learned lengths are used, the switch shows it and So far says In use",
    async run({ open, click, has, until, q, expect }) {
      was = await durations(q)
      expect(was && was.n > 0, `the sample has learned no lengths: ${JSON.stringify(was)}`)
      await open("/insights?tab=trends")
      await has("Adjust new estimates automatically")
      await has(`Learned from ${was.n} finished things.`)
      if (was.in_use) {
        await click("Adjust estimates")
        await waitFor(async () => !(await durations(q)).in_use)
      }
      await has(`Learned from ${was.n} finished things you timed`)
      await click("Adjust estimates")
      await has("Using learned durations")
      expect(await waitFor(async () => (await durations(q)).in_use), "the server doesn't use the learned lengths")
      await has(`In use from ${was.n} finished things you timed`)
      expect((await until(switchOn, 3000)) === "true", "the switch doesn't show on")
    },
  },
  {
    name: "off again: they're not used, and it stays so on a new load",
    async run({ open, click, has, until, q, expect }) {
      await open("/insights?tab=trends")
      await has(`In use from ${was.n} finished things you timed`)
      await click("Adjust estimates")
      await has("Stopped using learned durations")
      expect(await waitFor(async () => !(await durations(q)).in_use), "the server still uses the learned lengths")
      await open("/insights?tab=trends")
      await has(`Learned from ${was.n} finished things you timed`)
      expect((await until(`${switchOn} === "false"`, 3000)), "the switch shows on after a new load")
    },
  },
  {
    name: "the hours plans slip in are switched by the server alone; an unknown module is refused",
    async run({ q, c, request, expect }) {
      const on = await c("learn_module", { module: "energy", use: true })
      expect(/good and bad hours/.test(on.result.message), on.result.message)
      const off = await c("learn_module", { module: "energy", use: false })
      expect(/good and bad hours|Off/.test(off.result.message), off.result.message)
      expect((await q("learning")).energy.in_use === false, "energy left in use")
      const bad = await request("POST", "/api/c/learn_module", { module: "naps", use: true })
      expect(bad.status === 422, JSON.stringify(bad))
      if (was?.in_use) await c("learn_module", { module: "durations", use: true })
    },
  },
]
