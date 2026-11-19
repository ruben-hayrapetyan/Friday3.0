// A break's icon is the same everywhere: a calendar with an x, never the umbrella (19 Nov: "im confused on why there
// is an umbrella"; your answer "yes" to the same icon on the band, the Now bar, Settings and the rest). Read from the
// source: no file names the umbrella as an icon.
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { BREAK_ICON } from "./words"

const SRC = join(__dirname, "..")
const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })

describe("a break's icon", () => {
  it("is the calendar with an x", () => expect(BREAK_ICON).toBe("calendar-x"))
  it("is never the umbrella, anywhere in the app", () => {
    const named = files(SRC).filter((f) => /(name|icon)\s*[:=]\s*\{?\s*"umbrella"|:\s*"umbrella"/.test(readFileSync(f, "utf8")))
    expect(named.map((f) => f.slice(SRC.length + 1))).toEqual([])
  })
})
