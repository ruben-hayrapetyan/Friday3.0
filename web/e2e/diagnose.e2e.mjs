// Report a problem (tests/features.toml: diagnose): what breaks on a page (an error, a promise left failing, a part of
// the page that can't draw) is reported to the server by the page itself, and `diagnose` lists it in order next to
// what you did there (a pace saved and deleted in Settings → Advanced); a part that broke says so and Reload draws it
// again.

const said = async (q, kind, words) => (await q("diagnose", { hours: 1 })).filter((h) => h.kind === kind && h.summary.includes(words))
const waitFor = async (check, ms = 10_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
  }
  return null
}

export default [
  {
    name: "an error on the page is reported with the page it was on, and diagnose lists it",
    async run({ open, has, until, q, expect }) {
      await open("/settings/advanced")
      await has("Saved paces")
      const boom = `E2E boom ${Date.now()}`
      await until(`(setTimeout(() => { throw new Error(${JSON.stringify(boom)}) }), true)`)
      const found = await waitFor(async () => (await said(q, "report", boom))[0])
      expect(found, "the error wasn't reported to the server")
      expect(found.summary.startsWith("window #/settings/advanced"), `reported as "${found.summary}"`)
    },
  },
  {
    name: "a promise left failing is reported as one",
    async run({ open, has, until, q, expect }) {
      await open("/settings/advanced")
      await has("Saved paces")
      const why = `E2E rejected ${Date.now()}`
      await until(`(Promise.reject(new Error(${JSON.stringify(why)})), true)`)
      const found = await waitFor(async () => (await said(q, "report", why))[0])
      expect(found?.summary.startsWith("promise #/settings/advanced"), `reported as ${JSON.stringify(found)}`)
    },
  },
  {
    name: "a part that can't draw says so, is reported, and Reload draws it once it can",
    async run({ open, has, gone, click, answer, q, expect }) {
      const before = (await said(q, "report", "render #/settings/advanced")).length
      await answer({ paces: { default: "Normal", paces: null, now_label: "Normal", now_dials: {}, period_end: null } })
      await open("/settings/advanced")
      await has("Something on this page broke")
      await has("Nothing you saved is lost. Friday noted what happened so it can be fixed.")
      const found = await waitFor(async () => (await said(q, "report", "render #/settings/advanced")).length > before)
      expect(found, "the broken part wasn't reported")
      await answer(null)
      await click("Reload")
      await gone("Something on this page broke")
      await has("Saved paces")
    },
  },
  {
    name: "what you do on the page is listed in order: a pace saved, then deleted",
    async run({ open, type, click, has, gone, q, expect }) {
      await open("/settings/advanced")
      await type("New pace", "E2E Exam week")
      await click("Save the dials in use")
      await has("E2E Exam week", "main")
      const saved = await waitFor(async () => (await q("paces")).paces["E2E Exam week"])
      expect(saved, "the pace isn't on the server")
      const now = (await q("paces")).now_dials
      expect(JSON.stringify(saved) === JSON.stringify(now), `saved ${JSON.stringify(saved)}, not the dials in use ${JSON.stringify(now)}`)
      await click("Delete E2E Exam week")
      await gone("E2E Exam week", "main")
      expect(await waitFor(async () => !(await q("paces")).paces["E2E Exam week"]), "the pace is still on the server")
      const list = await q("diagnose", { hours: 1 })
      const at = (words) => list.findIndex((h) => h.kind === "command" && h.summary.includes(words))
      const add = at('pace_save name="E2E Exam week"')
      const drop = at('pace_delete name="E2E Exam week"')
      expect(add >= 0 && drop > add, `diagnose doesn't list the save then the delete (${add}, ${drop})`)
      const times = list.map((h) => h.at)
      expect(times.every((t, i) => i === 0 || times[i - 1] <= t), "diagnose isn't in order")
    },
  },
  {
    name: "diagnose refuses a stretch of no hours or over two weeks",
    async run({ request, expect }) {
      for (const hours of [0, -1, 24 * 14 + 1]) {
        const refused = await request("GET", `/api/q/diagnose?hours=${hours}`)
        expect(refused.status === 422 && refused.body.detail?.[0]?.loc?.includes("hours"), `hours=${hours}: ${JSON.stringify(refused)}`)
      }
      const fine = await request("GET", "/api/q/diagnose?hours=336")
      expect(fine.status === 200 && Array.isArray(fine.body), "two weeks is refused")
    },
  },
]
