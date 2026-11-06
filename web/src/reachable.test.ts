// Everything Friday can do, you can find (3 Nov, the CS 2112 UI lecture's discoverability: "make it possible for
// users to find all of the functionality"). 20 commands had no way in from the app; each now has one, or is one
// you never need to run yourself, said here with why. A new command fails this until it's one or the other.
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const ROOT = join(__dirname)
const app = (readdirSync(ROOT, { recursive: true }) as string[])
  .filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f) && !f.endsWith("schema.ts"))
  .map((f) => readFileSync(join(ROOT, f), "utf8"))
  .join("\n")
const api = JSON.parse(readFileSync(join(ROOT, "..", "openapi.json"), "utf8")) as { paths: Record<string, unknown> }
const commands = Object.keys(api.paths)
  .map((p) => p.match(/^\/api\/[cq]\/(\w+)$/)?.[1])
  .filter((c): c is string => !!c)

/** Never yours to run: Friday runs them, another app does, or they were for moving in once. */
export const BEHIND_THE_SCENES: Record<string, string> = {
  close_day: "the nightly job settles yesterday",
  materialize: "the nightly job makes repeats' new times",
  replan: "every change replans by itself",
  mac_sync: "the Mac app sends its calendars",
  mac_writes: "the Mac app asks what to change",
  mac_written: "the Mac app says what it changed",
  diagnose: "for working on Friday, from the command line",
  import_personal: "moving in from Todo List, done once",
  import_chroma_colors: "moving in from Chroma, done once",
  review_submit: "the Review answers task by task (review_task)",
  stats: "Insights shows the same from `insights`",
  checkin: "used only while state inference is on; no screen asks it yet",
  other_ways: "Other ways asks for one at a time (other_way) to show each as it comes; this is both, for the command line",
}

describe("every command has a way in", () => {
  it("reads the app and the API", () => {
    expect(commands.length).toBeGreaterThan(150)
    expect(app).toContain('"add"')
  })
  it("each is named by the app, or said here to run behind the scenes", () => {
    const named = (c: string) => new RegExp(`["'\`]${c}["'\`]`).test(app)
    expect(commands.filter((c) => !named(c) && !(c in BEHIND_THE_SCENES))).toEqual([])
  })
  it("nothing is listed behind the scenes that the app does run, or that no longer exists", () => {
    const named = (c: string) => new RegExp(`["'\`]${c}["'\`]`).test(app)
    expect(Object.keys(BEHIND_THE_SCENES).filter((c) => named(c) || !commands.includes(c))).toEqual([])
  })
  it("the eight that had no button now do", () => {
    for (const c of ["unshove", "template_save", "events_to_calendar", "category_merge", "beat_plan", "series_edit", "log", "changes"]) {
      expect(new RegExp(`["'\`]${c}["'\`]`).test(app), c).toBe(true)
    }
  })
})
