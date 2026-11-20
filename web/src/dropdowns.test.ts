// Every dropdown is Friday's own (20 Nov, the user: "i don't love how the calendar default dropdown menus look", then
// "all plain dropdowns"): the system's <select> drew a gray box and a list unlike every other menu in Friday. Settings →
// Calendars' "New events go to", an event's Calendar, Day starts and Bedtime, the AI model, the sleep log's day and
// Learning's five are `Menu` (components/fr/controls.tsx) now; a new <select> fails this.
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const ROOT = join(__dirname)
const files = (readdirSync(ROOT, { recursive: true }) as string[]).filter((f) => /\.tsx$/.test(f) && !/\.test\./.test(f))

describe("Friday's dropdowns", () => {
  it("are all Friday's own menu, never the system's <select>", () => {
    const native = files.filter((f) => /<select[\s>]/.test(readFileSync(join(ROOT, f), "utf8")))
    expect(native).toEqual([])
  })
})
