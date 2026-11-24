// Work archived once its due passed (tests/features.toml: pointless; 20 Nov, a user's notes: an exam's prep "2h late"
// after the exam; your answer: "Archive it, say so", H232). Two pieces of exam prep due an hour ago, archived by the
// server's own job loop; the Inbox says so with why, "Bring back" opens one again as still worth doing and "OK" lets
// the other's note go; each checked on the page and on the server.

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

/** `check()` once truthy, within `ms`. */
async function eventually(check, ms, said) {
  for (let end = Date.now() + ms; ; await sleep(1000)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

/** Presses the button named `name` inside the Inbox's archived note for `title`. */
const pressIn = (until, title, name) =>
  until(
    `(() => {
      const row = [...document.querySelectorAll('section[aria-label="Archived at its due"] [role=group]')].find((g) => g.getAttribute("aria-label") === ${JSON.stringify(title)})
      const button = row && [...row.querySelectorAll("button")].find((b) => b.textContent.trim() === ${JSON.stringify(name)})
      if (!button) return false
      button.click()
      return true
    })()`,
    10_000,
    `"${name}" beside ${title}`,
  )

const local = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
const ids = {}
const status = async (q, id) => (await q("item", { id })).item

export default [
  {
    name: "exam prep past its due is archived by the server and the Inbox says why",
    run: limit(240_000, async ({ open, has, text, q, c, expect }) => {
      const past = local(new Date(Date.now() - 3_600_000))
      ids.first = (await c("add", { title: "E2E midterm cram", preset: "Exam prep", due: past, duration_min: 60 })).result.item.id
      ids.second = (await c("add", { title: "E2E quiz review", preset: "Exam prep", due: past, duration_min: 45 })).result.item.id
      await eventually(async () => {
        const noted = (await q("inbox")).archived.map((a) => a.id)
        return noted.includes(ids.first) && noted.includes(ids.second)
      }, 180_000, "the job loop to archive both")
      expect((await status(q, ids.first)).status === "dropped", "the server didn't drop the first")
      await open("/inbox")
      await has("Archived: no point doing them now")
      await has("E2E midterm cram")
      await has("E2E quiz review")
      const shown = await text('section[aria-label="Archived at its due"]')
      expect(shown.includes("Its exam is over"), `the note doesn't say why: ${shown}`)
    }),
  },
  {
    name: "Bring back opens it again, still worth doing, and its note leaves",
    run: limit(120_000, async ({ open, has, until, q, expect }) => {
      await open("/inbox")
      await has("E2E midterm cram")
      await pressIn(until, "E2E midterm cram", "Bring back")
      await eventually(async () => (await status(q, ids.first)).status === "todo", 20_000, "the server to open it again")
      const item = await status(q, ids.first)
      expect(item.expires === false, `still pointless after its due: expires ${item.expires}`)
      expect(!(await q("inbox")).archived.some((a) => a.id === ids.first), "the server still notes it as archived")
      await until(`![...document.querySelectorAll('section[aria-label="Archived at its due"] [role=group]')].some((g) => g.getAttribute("aria-label") === "E2E midterm cram")`, 10_000, "its note gone from the page")
      await has("Archived: no point doing it now") // one left
    }),
  },
  {
    name: "OK lets the note go at once; the work stays archived",
    run: limit(120_000, async ({ open, has, until, q, expect }) => {
      await open("/inbox")
      await has("E2E quiz review")
      await pressIn(until, "E2E quiz review", "OK")
      await until(`!document.querySelector('section[aria-label="Archived at its due"]')`, 5_000, "the archived notes gone from the page")
      await eventually(async () => !(await q("inbox")).archived.some((a) => a.id === ids.second), 20_000, "the server to let the note go")
      expect((await status(q, ids.second)).status === "dropped", "OK brought the work back")
      await open("/inbox") // and it stays gone on a fresh load
      await until(`document.readyState === "complete" && !document.body.innerText.includes("E2E quiz review")`, 10_000, "no note on a fresh load")
    }),
  },
]
