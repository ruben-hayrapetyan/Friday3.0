// Rule clashes resolved (tests/features.toml: conflicts), in the Inbox: what Friday learned (here your sleep times)
// against a rule of yours (at least so many hours of sleep) is a decision there, with which side Friday would change
// and each answer; answering makes that change (the rule lowered, or the bedtimes earlier), it leaves the Inbox and
// isn't asked again while it stands. The sample sleeps 11:30pm to 7:30am on weeknights (8 h), 9 h on Friday night, 8 h
// on Saturday's and 7 h on Sunday's; a rule asking for more makes a question for each such run of nights.

const clashes = async (q) => (await q("status")).decisions.filter((d) => d.key.startsWith("learned:sleep:"))
const clash = async (q, key) => (await clashes(q)).find((d) => !key || d.key === key)
const WEEK = "learned:sleep:mon,tue,wed,thu" // 11:30pm to 7:30am: 8 hours
const rule = async (q) => (await q("settings")).rules.find((r) => r.type === "sleep_min")
const waitFor = async (check, ms = 60_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) {
    const found = await check()
    if (found) return found
  }
  return null
}
let sleep // the sample's own times, put back at the end

export default [
  {
    name: "a sleep rule your times don't keep is asked in the Inbox; lowering the rule lowers it and the question goes",
    async run({ open, click, has, gone, q, c, expect }) {
      sleep = (await q("settings")).sleep
      await c("rule_add", { text: "at least 9 hours of sleep" })
      expect((await rule(q))?.params.hours === 9, `the rule read as ${JSON.stringify(await rule(q))}`)
      const asked = await waitFor(() => clash(q, WEEK))
      expect(asked, `no decision about the weeknights: ${JSON.stringify((await clashes(q)).map((d) => d.key))}`)
      expect(!(await clash(q, "learned:sleep:fri")), "Friday night's 9 h is asked about")
      expect(asked.kind === "learned" && asked.update === "learned", `asked as ${asked.kind}/${asked.update}`)
      expect(asked.title === "Your sleep times leave 8 h 00 m asleep; your rule asks for 9 h", asked.title)
      const lower = asked.options.find((o) => o.id === "rule")
      const earlier = asked.options.find((o) => o.id === "bedtime")
      expect(lower?.label === "Lower the rule to 8 h" && earlier?.recommended, `the answers: ${JSON.stringify(asked.options)}`)
      await open("/inbox")
      await click(`${asked.title}${asked.detail}`) // the row: its title, then its days (Saturday's reads the same title)
      await has("To decide · What Friday learned, against a rule of yours", "div.fr-gutter")
      await has(asked.detail, "div.fr-gutter")
      expect(asked.detail.startsWith("Mondays, Tuesdays, Wednesdays and Thursdays: bed at 11:30pm, up at 7:30am."), asked.detail)
      await has("Friday would keep your rule and change what it learned.", "div.fr-gutter")
      await has(`${lower.label}: ${lower.detail}`, "div.fr-gutter")
      await has("Nothing waits on your answer: the plan goes on meanwhile.")
      await click(lower.label)
      await has("At least 8 h of sleep a night")
      expect(await waitFor(async () => (await rule(q))?.params.hours === 8, 10_000), `the rule is ${JSON.stringify((await rule(q))?.params)}`)
      expect(!(await clash(q, WEEK)), "the weeknights are still asked about")
      const left = await clashes(q)
      expect(left.length === 1 && left[0].key === "learned:sleep:sun" && left[0].title.includes("7 h 00 m") && left[0].title.includes("8 h"), `still asked: ${JSON.stringify(left.map((d) => d.title))}`)
      expect(JSON.stringify((await q("settings")).sleep) === JSON.stringify(sleep), "the bedtimes changed too")
    },
  },
  {
    name: "answered, it isn't asked again; asked anew, going to bed earlier moves every bedtime",
    async run({ open, click, has, gone, q, c, request, expect }) {
      const settled = await request("POST", "/api/c/conflict_resolve", { key: WEEK.replace(/^learned:/, ""), option: "rule" })
      expect(settled.status === 422 && settled.body.message.includes("that's settled already"), JSON.stringify(settled))
      const name = (await rule(q)).name
      await c("rule_remove", { name })
      expect(!(await waitFor(async () => (await clashes(q)).length > 0, 3000)), "asked with no sleep rule")
      await c("rule_add", { text: "at least 10 hours of sleep" })
      const asked = await waitFor(() => clash(q, WEEK))
      expect(asked?.title.includes("your rule asks for 10 h"), `asked: ${asked?.title}`)
      const wrong = await request("POST", "/api/c/conflict_resolve", { key: WEEK.replace(/^learned:/, ""), option: "nap" })
      expect(wrong.status === 422 && wrong.body.message.includes("no answer 'nap' to that"), JSON.stringify(wrong))
      const earlier = asked.options.find((o) => o.id === "bedtime")
      expect(earlier.label === "Go to bed at 9:30pm" || earlier.label === "Go to bed at 21:30", earlier.label)
      await open("/inbox")
      await click(`${asked.title}${asked.detail}`) // the row: its title, then its days
      await has(asked.detail, "div.fr-gutter")
      await click(earlier.label)
      const after = await waitFor(async () => {
        const now = (await q("settings")).sleep
        return ["mon", "tue", "wed", "thu"].every((d) => now[d].bedtime === "21:30") && now
      }, 10_000)
      expect(after, `the bedtimes are ${JSON.stringify((await q("settings")).sleep)}`)
      for (const [d, n] of Object.entries(after)) {
        expect(n.wake === sleep[d].wake, `${d}'s wake time changed`)
        if (!["mon", "tue", "wed", "thu"].includes(d)) expect(n.bedtime === sleep[d].bedtime, `${d}'s bedtime changed`)
      }
      expect((await rule(q)).params.hours === 10, "the rule changed")
      expect(!(await clash(q, WEEK)), "the weeknights are still asked about after going to bed earlier")
      await gone(asked.detail, "[role=list]") // its row; Saturday night's reads the same title, with its own days
    },
  },
  {
    name: "the sample's sleep and rules are put back",
    async run({ q, c, expect }) {
      const name = (await rule(q))?.name
      if (name) await c("rule_remove", { name })
      if (sleep) await c("settings_set", { key: "sleep", value: sleep })
      expect(!(await rule(q)), "the sleep rule is still there")
    },
  },
]
