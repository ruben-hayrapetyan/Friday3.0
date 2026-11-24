// Do I have time for this? (tests/features.toml: fitting): a to-do typed with a due says under the line whether it fits
// (fit, the quick check), and Check exactly plans it as a replan would; a new event (⌘N, the Mac app's New Event) says
// the same in its drawer, and an event that makes work late offers times where nothing gets later, one click away.
// Nothing is kept by checking. Checked on the page against the server's own answers.

const fit = async (base, body) => {
  const r = await fetch(`${base}/api/q/fit`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`fit: ${r.status} ${await r.text()}`)
  return r.json()
}
const local = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
const line = (out) => `${out.said}${out.exact ? "." : out.verdict === "late" ? ", even with every free minute." : "."}`
/** "4pm", "9:30am" → "16:00", "09:30". */
const hhmm = (said) => {
  const [, h, m = "00", half] = said.trim().toLowerCase().match(/^(\d{1,2})(?::(\d\d))?\s*(am|pm)?$/) ?? []
  const hour = (Number(h) % 12) + (half === "pm" ? 12 : 0) + (half ? 0 : Math.floor(Number(h) / 12) * 12)
  return `${String(hour).padStart(2, "0")}:${m}`
}
/** "2026-11-24T16:00" → "4pm", as the drawer shows a time. */
const spoken = (at) => {
  const [h, m] = at.slice(11, 16).split(":").map(Number)
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""}${h < 12 ? "am" : "pm"}`
}
const setDate = (evaluate, value) =>
  evaluate(`(() => {
    const el = document.querySelector('input[aria-label="Day"]')
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, "${value}")
    el.dispatchEvent(new Event("input", { bubbles: true }))
    el.dispatchEvent(new Event("change", { bubbles: true }))
  })()`)
const newEvent = (evaluate) => evaluate(`window.dispatchEvent(new CustomEvent("friday:host", { detail: { action: "newEvent" } }))`)
const draftTimes = (evaluate) =>
  evaluate(`(() => {
    const day = document.querySelector('input[aria-label="Day"]')?.value
    const time = (label) => document.querySelector('input[aria-label="' + label + '"]')?.value
    return { day, start: time("Starts"), end: time("Ends") }
  })()`)

export default [
  {
    name: "a to-do with a due says whether it fits; Check exactly plans it; nothing is added by checking",
    async run({ open, type, click, has, until, q, base, text, expect }) {
      const line0 = "E2E fit essay due fri 5pm ~3h"
      const before = (await q("items", { status: "all" })).length
      await open("/todo")
      await type("Add", line0)
      // the box is in a section, whose kind the check is made with: the server's answer for the line in each kind
      const kinds = [undefined, ...Object.keys((await q("settings")).presets)]
      const answers = await Promise.all(kinds.map((preset) => fit(base, { command: "add", input: { text: line0, ...(preset ? { preset } : {}) }, exact: false }).catch(() => null)))
      await until(`/Fits|Tight|Late|late/.test(document.querySelector("main").innerText) && !document.querySelector("main").innerText.includes("Checking whether you have time")`, 10_000, "the check under the line")
      const shown = await text("main")
      const quick = answers.find((a) => a && shown.includes(line(a)))
      expect(quick && !quick.exact, `the page's check matches none of the server's: ${JSON.stringify(answers.map((a) => a?.said))}`)
      await click("Check exactly")
      const kind = kinds[answers.indexOf(quick)]
      const exact = await fit(base, { command: "add", input: { text: line0, ...(kind ? { preset: kind } : {}) }, exact: true })
      await until(`![...document.querySelectorAll("main button")].some((b) => /^(Check exactly|Planning it)/.test(b.textContent.trim()))`, 60_000, "Check exactly gone once checked")
      // planned exactly, as a replan would: its verdict the server's (how many blocks move can differ run to run)
      const verdict = exact.said.split(":")[0]
      await has(`${verdict}:`, "main")
      expect((await q("items", { status: "all" })).length === before, "checking added a to-do")
    },
  },
  {
    name: "a new event says whether you have time for it, as the server says, and closing it keeps nothing",
    async run({ open, type, click, has, until, q, base, evaluate, expect }) {
      await open("/")
      await newEvent(evaluate)
      await has("New event")
      await type("Title", "E2E fit meeting") // with a title, the drawer asks
      await until(`document.body.innerText.toLowerCase().includes("do i have time for this?")`, 10_000, "the drawer asking whether you have time")
      const t = await draftTimes(evaluate)
      expect(/^\d{4}-\d\d-\d\d$/.test(t.day) && t.start && t.end, `the draft reads ${JSON.stringify(t)}`)
      const input = { title: "E2E fit meeting", when: "fixed", start: `${t.day}T${hhmm(t.start)}`, end: `${t.day}T${hhmm(t.end)}` }
      const said = await fit(base, { command: "add", input, exact: false })
      await has(line(said))
      await click("Close")
      await new Promise((r) => setTimeout(r, 500))
      expect(!(await q("plan")).fixed.some((f) => f.title === "E2E fit meeting"), "closing the draft kept the event")
    },
  },
  {
    name: "an event that makes work late offers times where nothing gets later; one clicked, it fits",
    async run({ open, type, click, has, until, q, c, base, planned, evaluate, expect }) {
      const due = new Date(Date.now() + 5 * 3_600_000)
      due.setMinutes(0, 0, 0)
      const work = (await c("add", { title: "E2E fit problem set", duration_min: 150, firmness: "hard", due: local(due) })).result.item
      try {
        await planned()
        const blocks = (await q("plan")).blocks.filter((b) => b.item_id === work.id)
        expect(blocks.length, "the problem set isn't planned")
        const first = blocks[0]
        const input = { title: "E2E fit clash", when: "fixed", start: first.start, end: first.end }
        const said = await fit(base, { command: "add", input, exact: false })
        expect(said.verdict === "late", `an event over the problem set's time doesn't make it late: ${JSON.stringify(said)}`)
        await open("/")
        await newEvent(evaluate)
        await type("Title", "E2E fit clash")
        await until(`document.body.innerText.toLowerCase().includes("do i have time for this?")`, 10_000, "the drawer asking whether you have time")
        await setDate(evaluate, first.start.slice(0, 10))
        await type("Ends", "23:30", { enter: true }) // first the end, so the start can move without the end before it
        await type("Starts", first.start.slice(11), { enter: true })
        await type("Ends", first.end.slice(11), { enter: true })
        await has(line(said))
        if (!said.instead?.length) return console.log("      (no time where nothing gets later: none offered)")
        await has("Nothing gets later at")
        const offered = await evaluate(`(() => {
          const row = [...document.querySelectorAll("span")].find((s) => s.firstChild?.textContent?.startsWith("Nothing gets later at"))
          const b = row?.querySelector("button")
          if (!b) return null
          b.click()
          return b.innerText
        })()`)
        expect(offered, "no time offered to click")
        await until(`document.querySelector('input[aria-label="Starts"]')?.value === ${JSON.stringify(spoken(said.instead[0].start))}`, 10_000, `the draft moved to ${said.instead[0].start}`)
        const moved = await fit(base, { command: "add", input: { ...input, start: said.instead[0].start, end: said.instead[0].end }, exact: false })
        expect(moved.verdict !== "late", `the time offered is late too: ${JSON.stringify(moved)}`)
        await has(line(moved))
        await click("Close")
      } finally {
        await c("drop", { id: work.id })
      }
    },
  },
]
