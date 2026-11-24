// The Now bar (tests/features.toml: now_view): what's on now, as the server's `now` says it, in the bar at the bottom
// of the plan; an event you're in, with until when and what's next; a to-do being timed, with its seconds, Pause and
// Done; each pressed as a person would, and what the server then has (`status`'s timer, the item) checked.

/** The server's local now plus `minutes`, as Friday writes times ("2026-11-24T13:05"). */
async function at(q, minutes) {
  const now = (await q("calendar", { days: 1 })).now
  const t = new Date(`${now.slice(0, 16)}:00Z`)
  return new Date(t.getTime() + minutes * 60_000).toISOString().slice(0, 16)
}

const bar = "[data-tour=now]"

/** A local time as the page writes it in 12-hour time: "2:08pm", and "2pm" too on the hour. */
function twelve(local) {
  const [h, m] = local.slice(11, 16).split(":").map(Number)
  const said = `${h % 12 || 12}`, half = h < 12 ? "am" : "pm"
  return [`${said}:${String(m).padStart(2, "0")}${half}`, ...(m === 0 ? [`${said}${half}`] : [])]
}
const find = async (q, title) => (await q("items", { status: "all" })).find((i) => i.title === title)

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

export default [
  {
    name: "an event you're in shows in the Now bar as the server's now says, with until when and what's next",
    async run({ open, has, text, q, c, planned, expect }) {
      const made = await c("add", { title: "E2E stand-up meeting", when: "fixed", start: await at(q, -90), end: await at(q, 50) })
      try {
        await planned()
        const now = await q("now")
        expect(now.current?.title === "E2E stand-up meeting" && now.current.fixed, `the server's now is ${now.current?.title}, not the meeting`)
        await open("/")
        await has("E2E stand-up meeting", bar)
        await has("Now, until", bar)
        const shown = await text(bar)
        expect(/(\d+:\d\d|\d+[hm]( \d+m)?) left/.test(shown), `the bar doesn't say how long is left: ${shown}`)
        expect(twelve(now.current.end).some((t) => shown.includes(`Now, until ${t}`)), `the bar's end isn't the server's ${now.current.end}: ${shown}`)
        if (now.next) expect(shown.includes(`then ${now.next.title}`), `the bar's "then" isn't the server's next (${now.next.title}): ${shown}`)
        else expect(shown.includes("then nothing else today"), `the server has nothing next, the bar says: ${shown}`)
      } finally {
        await c("drop", { id: made.result.item.id })
      }
      await planned()
      await open("/")
      const after = await text(bar)
      expect(!after.includes("E2E stand-up meeting"), "the bar still shows the deleted meeting")
    },
  },
  {
    name: "a to-do being timed shows its title, Timing since and Done; Pause stops the timer on the server",
    async run({ open, click, has, text, until, q, c, planned, expect, wait }) {
      const made = await c("add", { title: "E2E read chapter five", duration_min: 90, due: `${(await at(q, 3 * 1440)).slice(0, 10)}T17:00` })
      const id = made.result.item.id
      await planned()
      await c("start", { id })
      try {
        await open("/")
        await has("E2E read chapter five", bar)
        await has("Timing since", bar)
        expect((await q("now")).current?.item_id === id, "the server's now isn't the timed to-do")
        // the seconds tick on the page
        const first = await text(bar)
        await until(`document.querySelector(${JSON.stringify(bar)}).innerText.replace(/\\s+/g, " ") !== ${JSON.stringify(first)}`, 5_000, "the timer ticking")
        await click("Pause the timer (Space)")
        await eventually(async () => (await q("status")).timer === null, 10_000, "the timer stopped on the server", wait)
        await until(`!document.querySelector(${JSON.stringify(bar)}).innerText.includes("Timing since")`, 10_000, "the bar no longer timing")
        const item = await find(q, "E2E read chapter five")
        expect(item.status === "todo", `paused, it's ${item.status}, not still to do`)
      } finally {
        if ((await q("status")).timer) await c("stop", {})
      }
    },
  },
  {
    name: "Done in the Now bar stops the timer and finishes the to-do on the server",
    async run({ open, click, has, q, c, planned, expect, wait }) {
      const item = await find(q, "E2E read chapter five")
      expect(item, "no E2E read chapter five from the last test")
      await c("start", { id: item.id })
      try {
        await open("/")
        await has("Timing since", bar)
        await click("Done")
        await eventually(async () => (await find(q, "E2E read chapter five")).status === "done", 10_000, "the to-do done on the server", wait)
        expect((await q("status")).timer === null, "the timer still runs after Done")
        await planned()
        expect((await q("now")).current?.item_id !== item.id, "the server's now is still the finished to-do")
      } finally {
        if ((await q("status")).timer) await c("stop", {})
      }
    },
  },
]
