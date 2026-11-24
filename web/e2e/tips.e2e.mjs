// Pro tips (tests/features.toml: tips): a tip slides in a few seconds after Friday opens, stays ten seconds, and
// "Take me there" opens its page; it's counted when shown, so no other tip shows that day; × closes it at once.
// The first tip is a real one: two work events made in Friday ("Study for…") are the habit the first tip is about.

const local = (ms) => {
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
const TIP = "[role=status].fr-tip"
const made = []

export default [
  {
    name: "work made as events brings its tip; it slides in, is counted, and Take me there opens To-do",
    async run({ open, until, has, click, q, c, expect, planned }) {
      for (const [n, title] of [[1, "E2E Study for CHEM prelim"], [2, "E2E Study for MATH final"]]) {
        const start = Math.ceil(Date.now() / 3_600_000) * 3_600_000 + n * 86_400_000
        made.push((await c("add", { title, when: "fixed", start: local(start), end: local(start + 3_600_000) })).result.item.id)
      }
      await planned()
      const tip = await q("tips")
      expect(tip.id === "work_events", `the tip for work made as events isn't offered: ${JSON.stringify(tip)}`)
      await open("/")
      await until(`document.querySelector(${JSON.stringify(TIP)})?.innerText.includes(${JSON.stringify(tip.text)})`, 9000, "the tip sliding in")
      for (let i = 0; i < 20 && (await q("tips")).id; i++) await new Promise((r) => setTimeout(r, 250))
      expect((await q("tips")).id === null, "the tip shown wasn't counted: the server still offers a tip today")
      await click("Take me there")
      await until(`location.hash.startsWith("#/todo")`, 5000, "To-do opened from the tip")
      await until(`!document.querySelector(${JSON.stringify(TIP)})`, 3000, "the tip leaving once followed")
      await has("To-do", ".fr-title")
    },
  },
  {
    name: "one tip a day: opened again, no tip slides in",
    async run({ open, wait, until, q, expect }) {
      expect((await q("tips")).id === null, "a second tip is offered the same day")
      await open("/")
      await wait(6500)
      expect(await until(`!document.querySelector(${JSON.stringify(TIP)})`, 500), "a tip showed a second time the same day")
    },
  },
  {
    name: "× closes a tip at once, and one left alone slides out after its ten seconds",
    async run({ open, until, click, answer, wait, expect, c }) {
      const tip = { id: "rules", text: "Tell Friday how you like your days in Rules, in your own words.", page: "/rules" }
      await answer({ tips: tip })
      await open("/")
      await until(`document.querySelector(${JSON.stringify(TIP)})?.innerText.includes("Tell Friday how you like")`, 9000, "the tip sliding in")
      await click("Close tip")
      await until(`!document.querySelector(${JSON.stringify(TIP)})`, 1500, "the tip gone within a moment of ×")
      await open("/")
      const shown = await until(`document.querySelector(${JSON.stringify(TIP)}) ? performance.now() : 0`, 9000, "the tip sliding in again")
      await wait(8000)
      expect(await until(`!!document.querySelector(${JSON.stringify(TIP)})`, 500), "the tip left before its ten seconds")
      const left = await until(`!document.querySelector(${JSON.stringify(TIP)}) && performance.now()`, 6000, "the tip sliding out")
      expect(left - shown >= 9500 && left - shown < 12_500, `the tip stayed ${Math.round(left - shown)}ms, not ten seconds`)
      for (const id of made.splice(0)) await c("drop", { id })
    },
  },
]
