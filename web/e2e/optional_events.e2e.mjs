// Optional events (tests/features.toml: optional_events): an event opened from the calendar, then Edit, asks "Can work
// take its time?" — No, If work needs it, If I'm ahead (event_optional) — and says which it is now (event_mode); each
// choice is written as the rule in words would be, listed on the Rules page, and No takes it away; a broader rule
// that still reaches the event is named, with a way to Rules. Checked on the page and on the server.

const settle = async (check, what, ms = 15_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}

/** An event coming up on the page (not a class), opened in its drawer: its title. */
const openEvent = async ({ open, q, evaluate, click, has }) => {
  await open("/")
  const events = (await q("plan")).fixed.filter((f) => f.status === "todo" && new Date(f.start) > new Date() && f.event_kind !== "shove")
  const event = events.find((f) => /rocketry/i.test(f.title)) ?? events.find((f) => f.calendar !== "Cornell Classes") ?? events[0]
  if (!event) throw new Error("no event coming up in the sample")
  await evaluate(`document.querySelector('[data-block-key="F${event.id}"]').click()`)
  await has(event.title, ".fr-block-card")
  await click("Edit")
  await has("If I'm ahead")
  return event.title
}
const mode = async (q, title) => await q("event_mode", { title })
const pressed = (label) => `document.querySelector('[role=group][aria-label^="Can work take"] [aria-pressed=true]')?.textContent === ${JSON.stringify(label)}`

export default [
  {
    name: "an event's drawer says work keeps off it; If work needs it makes it optional, as a rule on the Rules page",
    async run(t) {
      const { click, has, until, q, open, expect } = t
      const title = await openEvent(t)
      expect((await mode(q, title)).mode === "kept", "the event isn't kept to begin with")
      await until(pressed("No"), 10_000, "No chosen to begin with")
      await has("Work keeps off it.")
      await click("If work needs it")
      await settle(async () => (await mode(q, title)).mode === "optional", "optional on the server")
      await until(pressed("If work needs it"), 10_000, "If work needs it chosen")
      await has("Friday uses its time only when work would be late otherwise")
      const said = (await mode(q, title)).rule
      expect(said && said.includes(title), `the rule says "${said}", not the event's title`)
      const rule = (await q("rules")).find((r) => r.sentence === said)
      expect(rule && rule.source === "you" && rule.enabled, `no rule "${said}" on the server`)
      await has(`From your rule “${said}”.`)
      await open("/rules")
      await has(said)
    },
  },
  {
    name: "If I'm ahead changes the same rule, and No takes it away",
    async run(t) {
      const { click, has, until, q, expect } = t
      const title = await openEvent(t)
      const count = (await q("rules")).length
      await click("If I'm ahead")
      await settle(async () => (await mode(q, title)).mode === "ahead", "only when ahead on the server")
      await until(pressed("If I'm ahead"), 10_000, "If I'm ahead chosen")
      await has("Friday leaves it free when you're ahead")
      expect((await q("rules")).length === count, "changing how it's optional made another rule")
      const said = (await mode(q, title)).rule
      await click("No")
      await settle(async () => (await mode(q, title)).mode === "kept", "kept on the server")
      await until(pressed("No"), 10_000, "No chosen")
      expect(!(await q("rules")).some((r) => r.sentence === said), `the rule "${said}" is still there`)
      expect((await q("rules")).length === count - 1, "No didn't take the rule away")
    },
  },
  {
    name: "a broader rule that still reaches the event is named in its drawer, with a way to Rules",
    async run(t) {
      const { click, has, until, q, c, expect } = t
      const added = await c("rule_add", { text: "rocketry is optional" })
      expect(added.ok !== false, "the broader rule wasn't added")
      try {
        const title = await openEvent(t)
        expect(/rocketry/i.test(title), `the event opened is ${title}, which "rocketry" doesn't reach`)
        const covered = (await mode(q, title)).covered_by
        expect(covered.length === 1, `the server names ${JSON.stringify(covered)} as reaching it`)
        await has(`Your rule “${covered[0]}” also reaches it.`)
        await click("Change it in Rules")
        await until(`location.hash.startsWith("#/rules")`, 10_000, "the Rules page")
        await has(covered[0])
      } finally {
        const rule = (await q("rules")).find((r) => r.source === "you" && /rocketry/i.test(r.sentence))
        if (rule) await c("rule_remove", { name: rule.name })
      }
    },
  },
]
