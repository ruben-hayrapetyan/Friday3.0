// Input speed in the browser (24 Nov, the user: "make sure to stress test on very loaded schedules as well as varying
// input speeds"; tests/features.toml: items). A person quicker than the page: ten to-dos typed into the add line one
// after another with no pause, Mark done pressed twice before the first press is answered, ⌘Z pressed three times
// at once. Each lands once, nothing errs, and the page ends showing what the server has.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function eventually(check, ms, said) {
  for (let end = Date.now() + ms; ; await sleep(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const all = async (q) => q("items", { status: "all" })
const named = async (q, prefix) => (await all(q)).filter((i) => i.title.startsWith(prefix))
const ERROR_TOAST = `[...document.querySelectorAll("[role=status], [role=alert]")].map((t) => t.innerText).join(" | ")`

export default [
  {
    name: "ten to-dos typed one after another with no pause each land once and all show",
    async run({ open, until, page, press, q, has, expect, evaluate }) {
      await open("/todo")
      await until(`(() => { const f = [...document.querySelectorAll("input, textarea")].find((f) => f.getAttribute("aria-label") === "Add" || f.getAttribute("placeholder")?.startsWith("Add")); if (!f) return false; f.focus(); return true })()`, 10_000, "the add line")
      for (let n = 0; n < 10; n++) {
        await page("Input.insertText", { text: `Fast ${n} ~30m due fri 5pm` })
        await press("Enter") // no waiting for the page between them
      }
      const landed = await eventually(async () => {
        const got = await named(q, "Fast ")
        return got.length >= 10 && got
      }, 30_000, "ten to-dos on the server")
      const titles = landed.map((i) => i.title).sort()
      expect(titles.length === 10, `${titles.length} landed: ${titles.join(", ")}`)
      expect(new Set(titles).size === 10, `one landed twice: ${titles.join(", ")}`)
      for (let n = 0; n < 10; n++) expect(titles.includes(`Fast ${n}`), `Fast ${n} is missing, or was read as another title: ${titles.join(", ")}`)
      expect(landed.every((i) => i.duration_min === 30), `lengths ${landed.map((i) => i.duration_min).join(", ")}`)
      for (let n = 0; n < 10; n++) await has(`Fast ${n}`)
      const toasts = await evaluate(ERROR_TOAST)
      expect(!/couldn|error|failed/i.test(toasts), `an error showed: ${toasts}`)
    },
  },
  {
    name: "Mark done pressed twice before the first answer finishes it once, with no error",
    async run({ open, until, q, has, expect, evaluate }) {
      const item = (await named(q, "Fast 0"))[0]
      await open(`/todo?item=${item.id}`)
      await has("Planned sessions")
      const pressed = await until(`(() => {
        const b = [...document.querySelectorAll('[data-panel=todo-detail] button')].find((x) => x.innerText.trim() === "Mark done")
        if (!b) return false
        b.click(); b.click()
        return true
      })()`, 10_000, "Mark done in the panel")
      expect(pressed, "no Mark done")
      await eventually(async () => (await named(q, "Fast 0"))[0].status === "done", 15_000, "it done on the server")
      await has("Open again", "[data-panel=todo-detail]")
      await sleep(1500) // a second press, had it gone through, would have answered by now
      expect((await named(q, "Fast 0"))[0].status === "done", "the second press opened it again")
      const toasts = await evaluate(ERROR_TOAST)
      expect(!/couldn|error|failed|isn't/i.test(toasts), `an error showed: ${toasts}`)
    },
  },
  {
    name: "⌘Z pressed three times at once undoes the last change once and says there's nothing more",
    async run({ open, until, page, press, q, has, gone, expect }) {
      await open("/todo")
      for (const title of ["Undo A", "Undo B", "Undo C"]) {
        await until(`(() => { const f = [...document.querySelectorAll("input, textarea")].find((f) => f.getAttribute("aria-label") === "Add" || f.getAttribute("placeholder")?.startsWith("Add")); if (!f) return false; f.focus(); return true })()`, 10_000, "the add line")
        await page("Input.insertText", { text: `${title} ~20m due fri 5pm` })
        await press("Enter")
        await eventually(async () => (await named(q, title)).length === 1, 15_000, `${title} on the server`)
        await has(title)
      }
      await until(`(document.activeElement?.blur(), document.body.click(), true)`, 2_000) // ⌘Z isn't the text field's
      await press("Meta+z")
      await press("Meta+z")
      await press("Meta+z")
      await eventually(async () => (await named(q, "Undo C")).length === 0, 15_000, "Undo C taken back on the server")
      await sleep(1500)
      const left = (await named(q, "Undo ")).map((i) => i.title).sort()
      expect(left.join() === "Undo A,Undo B", `left after three quick ⌘Z: ${left.join(", ")} (only the last change is undone)`)
      await gone("Undo C")
      await has("Undo A")
      await has("Undo B")
      await has("Nothing to undo")
    },
  },
]
