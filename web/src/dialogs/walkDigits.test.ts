// The walk's and the tour's numbers (dialogs/walkDigits.ts, setup.css, shell/guide.css; 13 Nov: clients read
// Pixelify's "6:15am" as "6:18am" and "12am" as "18am", and "fits" as "Ats"). Glass box: the digits-only face is
// registered once with the digits and the colon. Black box over the styles: every number shown on its own uses VT323,
// every pixel-font stack takes its digits from it, and the pixel font's joined letters are off.
import { readFileSync } from "node:fs"
import path from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { addWalkDigits, DIGITS_RANGE, resetWalkDigits, WALK_DIGITS } from "./walkDigits"

const css = (file: string) => readFileSync(path.resolve(__dirname, file), "utf8")
const rule = (text: string, selector: string) => {
  const at = text.indexOf(`${selector} {`)
  expect(at, `${selector} is styled`).toBeGreaterThanOrEqual(0)
  return text.slice(at, text.indexOf("}", at))
}

afterEach(() => resetWalkDigits())

describe("the walk's digits face", () => {
  it("is VT323 for 0–9 and the colon only, added once", () => {
    const added: { family: string; descriptors: FontFaceDescriptors }[] = []
    const fonts = { add: () => undefined }
    const make = (family: string, _source: string, descriptors: FontFaceDescriptors) => (added.push({ family, descriptors }), { family } as unknown as FontFace)
    addWalkDigits(fonts, make)
    addWalkDigits(fonts, make)
    expect(added).toHaveLength(1)
    expect(added[0].family).toBe(WALK_DIGITS)
    expect(added[0].descriptors.unicodeRange).toBe(DIGITS_RANGE)
    const [from, to] = DIGITS_RANGE.replace("U+", "").split("-").map((h) => Number.parseInt(h, 16))
    expect([from, to]).toEqual(["0".charCodeAt(0), ":".charCodeAt(0)])
  })

  it("is left out where there's no FontFace (the pixel font shows)", () => {
    expect(addWalkDigits(undefined, undefined)).toBeNull()
  })
})

describe("the walk's and the tour's styles", () => {
  const setup = css("setup.css")
  const guide = css("../shell/guide.css")

  it("show a time or number on its own in VT323", () => {
    expect(setup).toMatch(/--wk-digits: "VT323"/)
    for (const selector of [".st-time input", ".ob-tile b", ".st-big"]) expect(rule(setup, selector)).toContain("var(--wk-digits)")
  })

  it("take every digit in the pixel font from VT323 too", () => {
    expect(setup).toMatch(/--wk-pixel: "Walk Digits", "Pixelify Sans"/)
    expect(guide).toMatch(/--gd-pixel: "Walk Digits", "Pixelify Sans"/)
  })

  it("never join letters in the pixel font", () => {
    expect(rule(setup, ".wk-stage")).toContain("font-variant-ligatures: none")
    expect(rule(guide, ".gd-quests")).toContain("font-variant-ligatures: none")
  })
})
