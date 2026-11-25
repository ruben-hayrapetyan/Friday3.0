// The AI (tests/features.toml: ai), Settings → Integrations → AI: the box says it's ready, "Check it works" asks each
// model Friday uses and says what came back; a backup key is saved and removed; a key with a space in it
// is refused in words; choosing another AI is saved and the page says what it needs. The demo's AI is a stand-in, so
// nothing is asked of a real service. Every step checked on the page and on the server.

const llm = async (q) => (await q("inbox")).llm

const openAi = async ({ open, click, has }) => {
  await open("/settings/integrations")
  await has("Bring in your calendars")
  await click("AI, Ready")
  await has("Reads syllabi and mail")
}

export default [
  {
    name: "the AI's box says Ready, and Check it works says each model works",
    async run(t) {
      const { click, has, text, q, expect } = t
      expect((await llm(q)).ready, "the sample's AI isn't ready on the server")
      await openAi(t)
      await has("Friday reads with Claude.")
      await click("Check it works")
      const checks = await q("ai_check")
      expect(checks.length === 2 && checks.every((c) => c.ok), `the server's check: ${JSON.stringify(checks)}`)
      for (const c of checks) await has(`${c.model} (${c.job.toLowerCase()}): works`)
      expect(!(await text()).includes("Asking…"), "the check is still asking")
    },
  },
  {
    name: "a key with a space in it is refused in words and isn't kept",
    async run(t) {
      const { type, click, has, q, c, expect } = t
      if ((await llm(q)).key) await c("ai_key_set", { provider: "claude", key: "" }) // a run before left one
      await openAi(t)
      await type("Anthropic API key", "sk-ant not-a-key")
      await click("Save key")
      await has("A key has no spaces or line breaks in it: paste it again")
      expect(!(await llm(q)).key, "the server kept a key with a space in it")
    },
  },
  {
    name: "a backup key is saved and kept out of sight; Remove forgets it",
    async run(t) {
      const { type, click, has, until, q, expect } = t
      await openAi(t)
      await type("Anthropic API key", "sk-ant-e2e-only-a-test")
      await click("Save key")
      await has("A key is saved (kept in secrets.toml, never shown again).")
      expect((await llm(q)).key, "the server has no key after Save key")
      expect(!(await t.text()).includes("sk-ant-e2e-only-a-test"), "the key is shown on the page")
      await click("Remove")
      await until(`!document.body.innerText.includes("A key is saved")`, 10_000, "the key field back")
      expect(!(await llm(q)).key, "the server still has the key after Remove")
    },
  },
  {
    name: "choosing another AI is saved and says what it needs; choosing Claude again is ready again",
    async run(t) {
      const { click, has, until, q, expect } = t
      await openAi(t)
      await click("OpenAI")
      await until(`document.querySelector('[role=radio][aria-checked=true]')?.innerText.startsWith("OpenAI")`, 10_000, "OpenAI chosen")
      const chosen = (await q("settings")).llm
      expect(chosen.provider === "openai", `the server reads with ${chosen.provider}, not OpenAI`)
      await has("OpenAI API key")
      await click("Claude")
      await has("Friday reads with Claude.")
      expect((await q("settings")).llm.provider === "claude", "Claude wasn't chosen again on the server")
      expect((await llm(q)).ready, "the AI isn't ready again")
    },
  },
]
