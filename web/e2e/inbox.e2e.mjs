// The Inbox (tests/features.toml: inbox): Alex's lived-in sample has mail and calendar suggestions waiting, and one set
// aside as what Alex has already. Each is opened from its row as a person would and answered with the page's own
// buttons (Reject and its Undo, Edit then Accept, Update it, Add anyway, the R key); every answer checked on the page
// and on the server.

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

/** Opens the message whose row starts with `title`, from the list. */
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

/** Presses the button whose own words (not its icon or key hint) are `words`. */
const pressButton = (until, words) =>
  until(
    `(() => {
      const own = (b) => [...b.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim()
      const b = [...document.querySelectorAll("button")].find((b) => b.getBoundingClientRect().width > 0 && own(b) === ${JSON.stringify(words)})
      if (!b) return false
      b.click()
      return true
    })()`,
    10_000,
    `a button "${words}"`,
  )

/** Waits until the row for `title` says `words`. */
const rowShows = (until, title, words) =>
  until(`([...document.querySelectorAll('${LIST} [role=listitem]')].find((r) => r.querySelector("span span")?.textContent.trim() === ${JSON.stringify(title)})?.innerText ?? "").includes(${JSON.stringify(words)})`, 10_000, `the row ${title} to say ${words}`)

const rowTitles = (until) => until(`JSON.stringify([...document.querySelectorAll('${LIST} [role=listitem]')].map((r) => r.querySelector("span span")?.textContent.trim()))`, 10_000).then(JSON.parse)
const waiting = async (q) => (await q("inbox")).suggestions
const pendingTitled = async (q, title) => (await waiting(q)).find((s) => s.input.title === title)
const shared = {}

export default [
  {
    name: "the list shows every suggestion waiting on the server, and the count says how many",
    run: limit(90_000, async ({ open, has, until, q, expect }) => {
      const sugg = await waiting(q)
      expect(sugg.length >= 2, `the sample has ${sugg.length} suggestions waiting, not the mail and calendar ones`)
      shared.add = sugg.find((s) => s.command === "add")
      shared.edit = sugg.find((s) => s.command === "edit")
      expect(shared.add && shared.edit, "no add and edit suggestions in the sample")
      await open("/inbox")
      await has(`${shared.add.input.title}`, LIST)
      const titles = await rowTitles(until)
      for (const s of sugg) expect(titles.includes(s.input.title), `${s.input.title} isn't in the list: ${titles}`)
      const head = await until(`document.querySelector(".fr-page-head")?.innerText`, 5_000)
      expect(head.includes(`${titles.length} to deal with`), `the count says "${head}" for ${titles.length} rows`)
    }),
  },
  {
    name: "a suggestion opens with where it was found; Reject takes it out on the server, and Undo brings it back",
    run: limit(90_000, async ({ open, has, until, q, expect }) => {
      const s = shared.add
      await open("/inbox")
      await openRow(until, s.input.title)
      await has(`Found in ${s.origin}, ${s.source}`)
      await pressButton(until, "Reject")
      await rowShows(until, s.input.title, "Rejected") // answered at once, grayed in the list, the next one open
      await eventually(async () => !(await pendingTitled(q, s.input.title)), 15_000, "the server to reject it")
      await openRow(until, s.input.title)
      await has("Rejected. It won't come back unless the source changes.")
      await pressButton(until, "Undo")
      await eventually(async () => (await pendingTitled(q, s.input.title))?.id === s.id, 15_000, "Undo to bring it back on the server")
    }),
  },
  {
    name: "Edit, a new title, then Accept adds it under that title with what was found",
    run: limit(90_000, async ({ open, has, until, type, q, planned, expect }) => {
      const s = shared.add
      const title = `${s.input.title} (E2E)`
      await open("/inbox")
      await openRow(until, s.input.title)
      await has(`Found in ${s.origin}`)
      await pressButton(until, "Edit")
      await type("Title", title)
      await pressButton(until, "Accept")
      await rowShows(until, s.input.title, "Accepted")
      const made = await eventually(async () => (await q("items", { status: "all" })).find((i) => i.title === title), 15_000, `the server to add ${title}`)
      expect(made.due === s.input.due, `added due ${made.due}, not the ${s.input.due} found`)
      expect(!(await waiting(q)).some((x) => x.id === s.id), "still waiting on the server after Accept")
      expect(!(await q("items", { status: "all" })).some((i) => i.title === s.input.title), "added under the found title too")
      await planned()
    }),
  },
  {
    name: "a change to an event is answered with Update it, and the event moves on the server",
    run: limit(90_000, async ({ open, has, until, q, expect }) => {
      const s = shared.edit
      await open("/inbox")
      await openRow(until, s.input.title)
      await has("A change", LIST)
      await pressButton(until, "Update it")
      await rowShows(until, s.input.title, "Accepted")
      await eventually(async () => !(await waiting(q)).some((x) => x.id === s.id), 15_000, "the server to take the change")
      const event = (await q("events", { text: s.input.title })).find((e) => e.title === s.input.title)
      expect(event, `no event ${s.input.title} on the server`)
      if (s.input.start) expect(event.start === s.input.start, `the event starts ${event.start}, not the ${s.input.start} it moved to`)
    }),
  },
  {
    name: "set aside as what you have: Add anyway puts it back in the list, and R rejects it",
    run: limit(90_000, async ({ open, has, until, q, press, expect }) => {
      const aside = (await q("inbox")).set_aside
      expect(aside.length >= 1, "nothing set aside in the sample")
      const one = aside[0]
      await open("/inbox")
      await until(`(() => { const b = [...document.querySelectorAll("button[aria-expanded]")].find((b) => b.textContent.includes("Set aside: ${aside.length} you have already")); if (!b) return false; b.click(); return true })()`, 10_000, "the Set aside fold")
      await has(one.why, LIST)
      await pressButton(until, "Add anyway")
      const back = await eventually(async () => (await waiting(q)).find((s) => s.id === one.id), 15_000, "the server to put it back in the inbox")
      expect(back.duplicate_of === null, "brought back still marked a duplicate")
      await has(one.title, LIST)
      await openRow(until, back.input.title ?? one.title)
      await has(`Found in ${back.origin}`)
      await press("r")
      await rowShows(until, back.input.title ?? one.title, "Rejected")
      await eventually(async () => !(await waiting(q)).some((s) => s.id === one.id), 15_000, "R to reject it on the server")
    }),
  },
]
