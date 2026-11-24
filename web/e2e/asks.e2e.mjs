// Ask me later (tests/features.toml: asks; 9 Nov: Friday's questions go to the Inbox; "Not now" asks again once
// Friday has more to go on). Alex's Inbox asks to weigh the rules as Alex plans and which of two days looks better:
// each opened from its row, "Not now" pressed, and the question gone from the list and kept on the server with what it
// was based on, also on a fresh load; its toast's Undo brings it back.

const limit = (ms, run) => async (t) => {
  let timer
  const late = new Promise((_, fail) => (timer = setTimeout(() => fail(new Error(`the test took over ${ms / 1000}s`)), ms)))
  try {
    return await Promise.race([run(t), late])
  } finally {
    clearTimeout(timer)
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function eventually(check, ms, said) {
  for (let end = Date.now() + ms; ; await sleep(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const LIST = '[role=list][aria-label="Waiting for you"]'
const WEIGH = "Weigh your rules the way you plan"
const COMPARE = "Which version of the day looks better?"

const openRow = (until, title) =>
  until(
    `(() => {
      const row = [...document.querySelectorAll('${LIST} [role=listitem]')].find((r) => r.querySelector("span span")?.textContent.trim() === ${JSON.stringify(title)})
      if (!row) return false
      row.click()
      return true
    })()`,
    15_000,
    `the row ${title}`,
  )

const listed = (until, title) =>
  until(`[...document.querySelectorAll('${LIST} [role=listitem]')].some((r) => r.querySelector("span span")?.textContent.trim() === ${JSON.stringify(title)}) ? "yes" : "no"`, 10_000)

const later = async (q) => (await q("asks_later")).later

export default [
  {
    name: "Friday's questions are in the Inbox, each marked Question, and none is set aside yet",
    run: limit(60_000, async ({ open, has, until, q, expect }) => {
      expect(Object.keys(await later(q)).length === 0, "the sample starts with questions set aside")
      await open("/inbox")
      await has(WEIGH, LIST)
      await has(COMPARE, LIST)
      const meta = await until(`[...document.querySelectorAll('${LIST} [role=listitem]')].find((r) => r.innerText.includes(${JSON.stringify(WEIGH)}))?.innerText`, 5_000)
      expect(meta.includes("Question"), `the row doesn't say it's a question: ${meta}`)
    }),
  },
  {
    name: "Not now on a question takes it out of the list and keeps it on the server with its evidence",
    run: limit(90_000, async ({ open, has, click, until, q, expect }) => {
      const version = (await q("learning")).suggested?.version
      expect(version != null, "the sample has no new weighing of the rules to ask about")
      await open("/inbox")
      await openRow(until, WEIGH)
      await has("Approving changes how much each rule counts")
      await has("Not now: it leaves your Inbox")
      await click("Not now")
      const kept = await eventually(async () => (await later(q)).weights, 15_000, "the server to keep it")
      expect(kept === String(version), `kept with evidence ${kept}, not the weighing's version ${version}`)
      await until(`![...document.querySelectorAll('${LIST} [role=listitem]')].some((r) => r.innerText.includes(${JSON.stringify(WEIGH)}))`, 10_000, "the question gone from the list")
      await open("/inbox") // the server's, not the page's: gone on a fresh load too
      await has(COMPARE, LIST)
      expect((await listed(until, WEIGH)) === "no", "back in the list on a fresh load")
    }),
  },
  {
    name: "the toast's Undo brings a question set aside back to the server and the list",
    run: limit(90_000, async ({ open, has, click, until, q, expect }) => {
      await open("/inbox")
      await openRow(until, COMPARE)
      await has("One quick pick helps Friday learn what you prefer")
      await click("Not now")
      const day = (await q("questions")).comparisons[0]
      const kept = await eventually(async () => (await later(q)).compare, 15_000, "the server to keep the comparison set aside")
      expect(kept === String(day.id), `kept with evidence ${kept}, not the comparison's ${day.id}`)
      await click("Undo")
      await eventually(async () => (await later(q)).compare === undefined, 15_000, "Undo to take it back on the server")
      await has(COMPARE, LIST)
      expect((await later(q)).weights !== undefined, "Undo took back the other question too")
    }),
  },
]
