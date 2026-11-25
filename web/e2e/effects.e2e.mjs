// A suggestion's effect on the plan (tests/features.toml: effects), in the Inbox: an event waiting there says what
// accepting it would do (what it clashes with, the work planned in its time, the work it makes later) as the server
// works it out, and that declining changes nothing; at another time, that time is weighed. The sample has one event
// waiting (a calendar's change to an appointment); the other times are the page told the event is then (`answer`),
// and worked out by the real server.

const event = async (q) => (await q("inbox")).suggestions.find((s) => s.input.start && s.input.end && ["add", "edit"].includes(s.command))
const pane = "div.fr-gutter .fr-well"
const settled = `(() => { const w = [...document.querySelectorAll(${JSON.stringify(pane)})].find((x) => x.innerText.includes("If you accept")); return w && !w.innerText.includes("Working out what it changes") ? w.innerText.replace(/\\s+/g, " ") : null })()`

/** What the page should say for this effect. */
function says(effect) {
  if (!effect.event) return []
  const out = [...effect.clashes.map((c) => `Clashes with ${c.title}`), ...effect.later.map((l) => `${l.title} finishes about`)]
  if (effect.takes.length) out.push("Takes the time planned for", ...effect.takes.map((t) => t.title))
  if (!out.length) out.push("Nothing else changes: the time is free and no work finishes later.")
  return out
}

async function openIt({ open, click, has }, s) {
  await open("/inbox")
  await click(s.input.title)
  await has(s.input.title, "div.fr-gutter")
}

export default [
  {
    name: "an event waiting says what accepting it changes, as the server works it out, and that declining changes nothing",
    async run(t) {
      const { q, until, expect } = t
      const s = await event(q)
      expect(s, "the sample has no event waiting in the Inbox")
      const effect = await q("suggestion_effect", { id: s.id })
      expect(effect.event === true, "the server doesn't take it as an event")
      await openIt(t, s)
      const shown = await until(settled, 60_000, "the effect worked out")
      for (const words of says(effect)) expect(shown.includes(words), `"${words}" isn't said: ${shown}`)
      expect(shown.includes("If you decline") && shown.includes("Nothing in your plan changes."), "declining isn't said")
    },
  },
  {
    name: "at a time work is planned, it says that work moves, and names it",
    async run(t) {
      const { q, until, expect, answer } = t
      const s = await event(q)
      const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)
      const block = (await q("plan")).blocks.find((b) => !b.fixed && b.preset !== "Routine" && b.start > `${tomorrow}T08:00` && !b.background)
      expect(block, "no work planned from tomorrow to weigh against")
      const effect = await q("suggestion_effect", { id: s.id, start: block.start, end: block.end })
      expect(effect.takes.some((x) => x.title === block.title), `the server doesn't say ${block.title} moves: ${JSON.stringify(effect)}`)
      const inbox = await q("inbox")
      await answer({ inbox: { ...inbox, suggestions: inbox.suggestions.map((x) => (x.id === s.id ? { ...x, input: { ...x.input, start: block.start, end: block.end } } : x)) } })
      await openIt(t, s)
      const shown = await until(settled, 60_000, "the effect worked out")
      for (const words of says(effect)) expect(shown.includes(words), `"${words}" isn't said: ${shown}`)
      expect(!shown.includes("Nothing else changes"), "it says nothing changes over planned work")
    },
  },
  {
    name: "over another event, it says it clashes with it",
    async run(t) {
      const { q, until, expect, answer } = t
      const s = await event(q)
      const fixed = (await q("plan")).fixed.find((e) => e.id !== s.input.id && e.start && e.end && !e.background && new Date(e.start) > new Date())
      expect(fixed, "no event ahead to clash with")
      const effect = await q("suggestion_effect", { id: s.id, start: fixed.start, end: fixed.end })
      expect(effect.clashes.some((c) => c.title === fixed.title), `the server finds no clash with ${fixed.title}: ${JSON.stringify(effect)}`)
      const inbox = await q("inbox")
      await answer({ inbox: { ...inbox, suggestions: inbox.suggestions.map((x) => (x.id === s.id ? { ...x, input: { ...x.input, start: fixed.start, end: fixed.end } } : x)) } })
      await openIt(t, s)
      const shown = await until(settled, 60_000, "the effect worked out")
      expect(shown.includes(`Clashes with ${fixed.title}`), `the clash isn't said: ${shown}`)
    },
  },
  {
    name: "a to-do waiting has no effect to weigh; the server refuses what isn't waiting or ends before it starts",
    async run(t) {
      const { q, request, expect, until, wait } = t
      const todo = (await q("inbox")).suggestions.find((x) => !x.input.start && x.command === "add")
      if (todo) {
        expect((await q("suggestion_effect", { id: todo.id })).event === false, "a to-do is weighed as an event")
        await openIt(t, todo)
        await wait(1500)
        expect(await until(`![...document.querySelectorAll(${JSON.stringify(pane)})].some((x) => x.innerText.includes("If you accept"))`, 500), "a to-do says what accepting it changes")
      }
      const none = await request("GET", "/api/q/suggestion_effect?id=999999")
      expect(none.status === 422 && none.body.message.includes("no pending suggestion 999999"), JSON.stringify(none))
      const s = await event(q)
      const back = await request("GET", `/api/q/suggestion_effect?id=${s.id}&start=${s.input.end}&end=${s.input.start}`)
      expect(back.status === 422 && back.body.field === "end", JSON.stringify(back))
    },
  },
]
