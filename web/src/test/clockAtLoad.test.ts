// The screen tests run as this week's Thursday (setup.ts shifts the page's Date in beforeAll), so a screen test that
// reads the clock while its file loads reads the real one, a day or more off the page's: Account's "Looked 5 minutes
// ago" read "in a day" on a Friday (13 Nov). Read the clock inside a test or a function a test calls, never at the
// top of the file.
import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

const SRC = path.resolve(__dirname, "..")

function screenTests(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return name === "node_modules" ? [] : screenTests(full)
    return name.endsWith(".screen.test.tsx") ? [full] : []
  })
}

/** Lines at the top of a file (not indented, so not inside a function or test) that read the clock as it loads. */
export function clockAtLoad(text: string): string[] {
  // not indented: not inside a test; no arrow or function on the line: not read later, when called
  return text.split("\n").filter((line) => !/^\s/.test(line) && !/=>|function\b/.test(line) && /Date\.now\(\)|new Date\(/.test(line)).map((line) => line.trim())
}

describe("the screen tests", () => {
  it("never read the clock while their file loads", () => {
    const offenders = screenTests(SRC).flatMap((file) => clockAtLoad(readFileSync(file, "utf8")).map((line) => `${path.relative(SRC, file)}: ${line}`))
    expect(offenders).toEqual([])
  })

  it("catches a status made at the top of a file, and lets one made when asked be", () => {
    expect(clockAtLoad('const idle: Status = { last_checked: new Date(Date.now() - 300000).toISOString() }')).toHaveLength(1)
    expect(clockAtLoad("const idle = (): Status => ({ last_checked: new Date(Date.now() - 300000).toISOString() })")).toEqual([])
    expect(clockAtLoad('it("x", () => {\n  const now = Date.now()\n})')).toEqual([])
  })
})
