// What Friday learns (tests/features.toml: learning), in the Inbox, Insights and Settings → Advanced: Insights says how
// many of its questions wait and links to them; a day to compare is picked (or skipped) in the Inbox and counted; a new
// weighing of your rules is approved there, its weights then in use (and listed in Settings → Advanced → Learning);
// Reset weights puts them back; the learning modes are menus that the server keeps. The sample has a suggestion and
// days to compare waiting.

const waitFor = async (check, ms = 15_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const WEIGH = "Weigh your rules the way you plan"
const COMPARE = "Which version of the day looks better?"

export default [
  {
    name: "Insights says how many questions about what Friday learned wait, and the link opens the Inbox",
    async run({ open, click, has, until, q, expect }) {
      const learning = await q("learning")
      expect(learning.suggested, "the sample has no suggestion waiting")
      await open("/insights?tab=trends")
      await has("What Friday learned")
      const said = await until(`[...document.querySelectorAll("a")].map((a) => a.innerText).find((t) => /question.* about what Friday learned wait/.test(t))`, 10_000, "the link to the questions")
      const n = Number(said.match(/^(\d+)/)[1])
      expect(n >= 1, said)
      await click(said.trim())
      await until(`location.hash.startsWith("#/inbox")`, 5000, "the Inbox")
      await has(WEIGH, "[role=list]")
    },
  },
  {
    name: "a day to compare: Pick A is sent for that day and counted; Skip on the next is counted as skipped",
    async run({ open, click, has, q, expect }) {
      const before = await q("learning")
      const asked = (await q("questions")).comparisons
      expect(asked.length >= 2, `${asked.length} days to compare`)
      const last = (await q("log_list", { limit: 1 }))[0]?.id ?? 0
      await open("/inbox")
      await click(COMPARE)
      await has("Both finish the same work, placed differently around what can't move.")
      await click("Pick A")
      const sent = await waitFor(async () => (await q("log_list", { limit: 5 })).find((e) => e.command === "compare_answer" && e.id > last))
      expect(sent?.input.id === asked[0].id && sent.input.answer === "a", `sent ${JSON.stringify(sent?.input)} for day ${asked[0].id}`)
      expect(await waitFor(async () => (await q("learning")).comparisons === before.comparisons + 1), "the answer wasn't counted")
      expect(!(await q("questions")).comparisons.some((c) => c.id === asked[0].id), "the day is still asked about")
      await open("/inbox")
      await click(COMPARE)
      await click("Skip")
      const skipped = await waitFor(async () => (await q("log_list", { limit: 5 })).find((e) => e.command === "compare_answer" && e.input.answer === "skip"))
      expect(skipped?.input.id === asked[1].id, `skipped ${JSON.stringify(skipped?.input)}`)
      expect((await q("learning")).comparisons === before.comparisons + 1, "a skip was counted as an answer")
    },
  },
  {
    name: "Approve on the new weighing puts it in use; Advanced lists its weights; Reset weights puts them back",
    async run({ open, click, has, gone, q, request, expect }) {
      const learning = await q("learning")
      const suggested = learning.suggested
      await open("/inbox")
      await click(WEIGH)
      await has("Approving changes how much each rule counts when Friday plans.", "div.fr-gutter")
      await click("Approve")
      await has("Applied what Friday learned")
      const now = await waitFor(async () => {
        const l = await q("learning")
        return l.version === suggested.version && !l.suggested && l
      })
      expect(now, `not in use: ${JSON.stringify((await q("learning")).suggested)}`)
      for (const change of suggested.changes) expect(Math.abs(now.multipliers[change.rule] - change.to) < 0.01, `${change.rule} is ×${now.multipliers[change.rule]}, not ×${change.to}`)
      const again = await request("POST", "/api/c/learn_apply", { version: suggested.version })
      expect(again.status === 422 && again.body.message.includes(`no suggested profile version ${suggested.version}`), JSON.stringify(again))
      await gone(WEIGH, "[role=list]")
      await open("/settings/advanced")
      const first = suggested.changes[0]
      await has(`${first.rule.replaceAll("_", " ")} ×${now.multipliers[first.rule].toFixed(2)}`)
      await click("Reset weights")
      await has("Reset weights")
      expect(await waitFor(async () => Object.values((await q("learning")).multipliers).every((v) => Math.abs(v - 1) < 0.01)), "the weights weren't put back")
      await gone(`${first.rule.replaceAll("_", " ")} ×`)
    },
  },
  {
    name: "a learning mode picked in Settings → Advanced is kept by the server",
    async run({ open, click, has, q, c, expect }) {
      const learn = (await q("settings")).learn
      await open("/settings/advanced")
      await has("Learned lengths")
      await click("Missing rules…")
      await click(learn.proposals === "ask" ? "Don't propose" : "Propose, I decide")
      const want = learn.proposals === "ask" ? "off" : "ask"
      expect(await waitFor(async () => (await q("settings")).learn.proposals === want), `proposals is ${(await q("settings")).learn.proposals}, not ${want}`)
      await has("Learning saved")
      await c("settings_set", { key: "learn", value: learn })
    },
  },
  {
    name: "the server refuses turning down what isn't suggested, and answering a day that isn't asked",
    async run({ request, expect }) {
      const reject = await request("POST", "/api/c/learn_reject", { version: 999 })
      expect(reject.status === 422 && reject.body.message.includes("no suggested profile version 999"), JSON.stringify(reject))
      const day = await request("POST", "/api/c/compare_answer", { id: 999_999, answer: "a" })
      expect(day.status === 422 && day.body.message.includes("no comparison 999999"), JSON.stringify(day))
      const reset = await request("POST", "/api/c/learn_reset", { module: "naps" })
      expect(reset.status === 422, JSON.stringify(reset))
    },
  },
]
