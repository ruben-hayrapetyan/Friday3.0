// Copies and going over what came in (tests/features.toml: checking), in the Inbox (the old /inbox/check opens it): a
// task on your list twice is a message; Keep the chosen one keeps the one picked, the other's time moving onto it;
// They're different keeps both and stops asking. Go over everything again lists each task Friday brought in from your
// calendars, a message each: Keep it, Take it off my list (dropped; the calendar keeps its event), or Keep all.

const waitFor = async (check, ms = 15_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const item = async (q, id) => (await q("items", { status: "all" })).find((i) => i.id === id)
const group = async (q, title) => (await q("duplicates")).groups.find((g) => g.items.some((i) => i.title === title))
const p = (n) => String(n).padStart(2, "0")
/** Opens the Inbox's go-over message for `title` (the same task can also be another message: a gap to account for). */
const goOver = (until, title) =>
  until(`(() => { const r = [...document.querySelectorAll("[role=list] [role=listitem]")].find((x) => x.innerText.includes(${JSON.stringify(title)}) && x.innerText.includes("Go over")); return r ? (r.click(), true) : false })()`, 10_000, `the go-over of ${title}`)
const local = (ms) => {
  const d = new Date(ms)
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export default [
  {
    name: "a task on the list twice is asked about; Keep the chosen one keeps it and moves the other's time onto it",
    async run({ open, click, has, gone, until, q, c, day, expect }) {
      const add = async () => (await c("add", { title: "E2E Lab report 7", preset: "Assignment", duration_min: 120, due: `${day(5)}T17:00` })).result.item
      const [first, second] = [await add(), await add()]
      await c("log", { id: second.id, start: local(Date.now() - 3 * 3_600_000), end: local(Date.now() - 3 * 3_600_000 + 30 * 60_000) })
      const found = await waitFor(() => group(q, "E2E Lab report 7"))
      expect(found && found.items.map((i) => i.id).sort().join() === [first.id, second.id].sort().join(), `copies: ${JSON.stringify(found)}`)
      expect(found.keep === second.id, `the server would keep ${found.keep}, not the one with time logged`)
      await open("/inbox/check")
      await until(`location.hash.startsWith("#/inbox")`, 5000, "the Inbox")
      await click("E2E Lab report 7")
      await has("Copies · on your list 2 times", "div.fr-gutter")
      await has("Pick the one to keep")
      // keep the first one instead: the second's half hour moves onto it
      await until(`(() => { const r = [...document.querySelectorAll("input[type=radio]")].filter((x) => x.getAttribute("aria-label")?.startsWith("Keep E2E Lab report 7")); const b = r.find((x) => !x.checked); return b ? (b.click(), true) : false })()`, 5000, "the other copy's radio")
      await click("Keep the chosen one")
      expect(await waitFor(async () => (await item(q, second.id))?.status === "dropped"), "the copy not kept wasn't dropped")
      const kept = await item(q, first.id)
      expect(kept.status === "todo" && kept.done_min === 30, `kept: ${kept.status}, ${kept.done_min} min done`)
      expect(!(await group(q, "E2E Lab report 7")), "still asked about")
      await gone("E2E Lab report 7", "[role=list]")
      await c("drop", { id: first.id })
    },
  },
  {
    name: "They're different keeps both and stops asking about them",
    async run({ open, click, has, gone, q, c, day, expect }) {
      const add = async () => (await c("add", { title: "E2E Reading response", preset: "Assignment", duration_min: 60, due: `${day(6)}T12:00` })).result.item
      const both = [await add(), await add()]
      expect(await waitFor(() => group(q, "E2E Reading response")), "the copies aren't asked about")
      await open("/inbox")
      await click("E2E Reading response")
      await has("Copies · on your list 2 times", "div.fr-gutter")
      await click("They’re different")
      await has("Kept apart")
      expect(await waitFor(async () => !(await group(q, "E2E Reading response"))), "still asked about")
      for (const i of both) expect((await item(q, i.id)).status === "todo", `${i.id} isn't kept`)
      await gone("E2E Reading response", "[role=list]")
      for (const i of both) await c("drop", { id: i.id })
    },
  },
  {
    name: "Go over everything again lists what came from calendars; Keep it, Take it off my list, then Keep all",
    async run({ open, click, has, until, q, expect }) {
      expect((await q("to_review")).items.length === 0, "a go-over is already under way")
      await open("/inbox")
      await click("Go over everything again")
      const going = await waitFor(async () => {
        const r = await q("to_review")
        return r.started && r.items.length >= 3 && r
      })
      expect(going, `nothing to go over: ${JSON.stringify(await q("to_review")).slice(0, 200)}`)
      const [keep, off] = going.items
      expect(going.items.every((i) => going.sources[i.id] && going.sources[i.id] !== "you"), "something of yours is gone over")
      await goOver(until, keep.title)
      await has("Going over what Friday brought in", "div.fr-gutter")
      await has(keep.title, "div.fr-gutter")
      await click("Keep it")
      expect(await waitFor(async () => !(await q("to_review")).items.some((i) => i.id === keep.id)), "kept, it's still to go over")
      expect((await item(q, keep.id)).status === "todo", "kept, it isn't on the list")
      await goOver(until, off.title)
      await has(off.title, "div.fr-gutter")
      await has("Going over what Friday brought in", "div.fr-gutter")
      await click("Take it off my list")
      expect(await waitFor(async () => (await item(q, off.id))?.status === "dropped"), "taken off, it's still on the list")
      const left = (await q("to_review")).items.length
      if (left > 1) {
        await has(`${left} left to go over.`)
        await click(`Keep all ${left}`)
        expect(await waitFor(async () => (await q("to_review")).items.length === 0), "Keep all left some")
      }
    },
  },
  {
    name: "the server refuses keeping and dropping the same copy, and copies that aren't there",
    async run({ request, expect }) {
      const same = await request("POST", "/api/c/duplicates_merge", { groups: [{ keep: 1, drop: [1] }] })
      expect(same.status === 422, JSON.stringify(same))
      const gone = await request("POST", "/api/c/duplicates_merge", { groups: [{ keep: 999_998, drop: [999_999] }] })
      expect(gone.status === 422, JSON.stringify(gone))
    },
  },
]
