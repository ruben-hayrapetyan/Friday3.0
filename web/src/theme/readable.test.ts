// Readable text (3 Nov, measured against the CS 2112 UI lecture: "low contrast text is hard to read"; the grays for
// secondary words were 2.7:1 and 2.1:1 on the page, and text went down to 9px). Words are at least 11px; the grays
// they're written in are at least 4.5:1, on the page and on cards, in light and dark and in Setup.
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { contrast, mix, rgb } from "./contrast"
import { NEUTRAL, PAPER } from "./look"

// Read from disk: vitest hands CSS imports over empty.
const ROOT = join(__dirname, "..")
const sources = Object.fromEntries(
  (readdirSync(ROOT, { recursive: true }) as string[])
    .filter((f) => /\.(ts|tsx|css)$/.test(f) && !/\.test\./.test(f) && !f.endsWith("schema.ts"))
    .map((f) => [`../${f}`, readFileSync(join(ROOT, f), "utf8")]),
)
const SETUP = { bg: "#1b1a2b", text: "#f2ead8" } // dialogs/setup.css: Setup's own night palette
const LOOKS = { light: PAPER.light, dark: PAPER.dark, setup: [SETUP.bg, SETUP.bg, SETUP.text] } as const

describe("the contrast maths (glass box)", () => {
  it("black on white is 21, a color on itself is 1", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5)
    expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5)
  })
  it("is the same either way round", () => {
    expect(contrast("#336699", "#eeeeee")).toBeCloseTo(contrast("#eeeeee", "#336699"), 10)
  })
  it("matches WCAG's own worked value for #767676 on white (4.54)", () => {
    expect(contrast("#767676", "#ffffff")).toBeCloseTo(4.54, 2)
  })
  it("a mix's ends are its colors", () => {
    expect(mix("#e8ebe7", "#0f1113", 100).map((c) => Math.round(c * 255))).toEqual(rgb("#e8ebe7").map((c) => Math.round(c * 255)))
    expect(mix("#e8ebe7", "#0f1113", 0).map((c) => Math.round(c * 255))).toEqual(rgb("#0f1113").map((c) => Math.round(c * 255)))
  })
  it("more text in the mix is never less readable", () => {
    for (const [bg, , text] of Object.values(LOOKS)) {
      let last = 0
      for (let p = 0; p <= 100; p += 5) {
        const now = contrast(mix(text, bg, p), bg)
        expect(now).toBeGreaterThanOrEqual(last - 1e-9)
        last = now
      }
    }
  })
})

describe("the grays (black box)", () => {
  for (const [look, [page, card, text]] of Object.entries(LOOKS)) {
    it(`${look}: every gray for words is at least 4.5:1 on the page and on cards`, () => {
      for (const shade of [100, 200, 300, 400, 500] as const) {
        const gray = mix(text, page, NEUTRAL[shade])
        expect(contrast(gray, page), `${shade} on the page`).toBeGreaterThanOrEqual(4.5)
        expect(contrast(gray, card), `${shade} on a card`).toBeGreaterThanOrEqual(4.5)
      }
    })
    it(`${look}: 600, for icons and borders, is at least 3:1`, () => {
      expect(contrast(mix(text, page, NEUTRAL[600]), page)).toBeGreaterThanOrEqual(3)
      expect(contrast(mix(text, page, NEUTRAL[600]), card)).toBeGreaterThanOrEqual(3)
    })
  }
  it("the grays still step down, so there's a hierarchy", () => {
    const shares = [100, 200, 300, 400, 500, 600, 700, 800, 900].map((n) => NEUTRAL[n as keyof typeof NEUTRAL])
    expect(shares).toEqual([...shares].sort((a, b) => b - a))
  })
  it("Setup's own grays are the app's", () => {
    const css = sources["../dialogs/setup.css"]
    for (const shade of [200, 300, 400, 500, 600] as const) {
      expect(css).toContain(`--color-neutral-${shade}: color-mix(in oklch, ${SETUP.text} ${NEUTRAL[shade]}%, ${SETUP.bg});`)
    }
  })
})

describe("every screen (the whole app's source)", () => {
  const lines = Object.entries(sources).flatMap(([path, text]) => text.split("\n").map((line, i) => ({ at: `${path}:${i + 1}`, line })))
  it("reads every file", () => {
    expect(Object.keys(sources)).toContain("../plan/Pieces.tsx")
    expect(Object.keys(sources).length).toBeGreaterThan(100)
  })
  it("no text is under 11px", () => {
    const small = lines.filter(({ line }) => {
      const sizes = [...line.matchAll(/fontSize: ?([\d.]+)\b|font-size: ?([\d.]+)px/g)].map((m) => Number(m[1] ?? m[2]))
      return sizes.some((s) => s < 11)
    })
    expect(small.map((s) => s.at)).toEqual([])
  })
  it("no words are in the grays for icons and lines", () => {
    // `color:` (not background or border) in 600 or darker, other than on an icon
    const faint = lines.filter(({ line }) => /[^-]color: ?"var\(--color-neutral-[6-9]00\)"/.test(line) && !/<Icon|ph ph-/.test(line))
    expect(faint.map((f) => f.at)).toEqual([])
  })
})
