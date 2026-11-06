// Buttons that don't move with the text beside them (5 Nov: "when i'm trying to go far ahead and want to click it a lot
// of times, its annoying how it moves with the length of the text… this kind of 'buttons moving with text' is really
// annoying"). A button you press again and again comes before text that changes, or after text of a fixed width.
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { LengthStepper } from "@/todo/Pickers"

const root = join(__dirname, "..")
const read = (path: string) => readFileSync(join(root, path), "utf8")
const between = (text: string, from: string, to: string) => text.slice(text.indexOf(from), text.indexOf(to, text.indexOf(from)))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return name.endsWith(".tsx") && !name.includes(".test.") ? [path] : []
  })
}

describe("the Plan header's day arrows (glass box)", () => {
  const header = between(read("plan/PlanPage.tsx"), "function Header", "\n}\n")
  it("come before the date, whose length changes as you step", () => {
    expect(header.indexOf('aria-label="Previous"')).toBeGreaterThan(-1)
    expect(header.indexOf('aria-label="Next"')).toBeLessThan(header.indexOf("rangeTitle("))
    expect(header.indexOf('aria-label="Next"')).toBeLessThan(header.indexOf("subTitle("))
  })
  it("and the notes pill sits past the spacer, with the controls on the right, not after the date", () => {
    expect(header.indexOf("<Attention")).toBeGreaterThan(header.indexOf("flex: 1, minWidth: 0"))
  })
})

describe("− and + steppers (glass box)", () => {
  // Every number between a − and a + has a set width: a minimum let "10h 45m" push the + along.
  const steppers = sources(root).flatMap((path) => {
    const text = readFileSync(path, "utf8")
    return [...text.matchAll(/<Icon name="minus" \/>\s*<\/button>\s*<span([^>]*)>/g)].map((m) => ({ path, span: m[1] }))
  })
  it("are found", () => expect(steppers.length).toBeGreaterThanOrEqual(6))
  it.each(steppers.map((s) => [s.path.replace(root, ""), s.span]))("%s: its number has a fixed width", (_path, span) => {
    expect(span).toMatch(/\bwidth: \d+/)
    expect(span).not.toMatch(/minWidth/)
    expect(span).toMatch(/flex: "none"/)
  })
})

describe("the estimate's −15m … +1h (glass box)", () => {
  const nudge = read("components/EstimateNudge.tsx")
  it("come before the 'expected · left' text that changes as you press them", () => {
    expect(nudge.indexOf("STEPS.map(")).toBeLessThan(nudge.indexOf("expected ·"))
  })
})

describe("a length's − and + (black box)", () => {
  const html = (min: number) => renderToStaticMarkup(<LengthStepper value={min} onSave={() => {}} />)
  it("show the length between them in the same width, short or long", () => {
    const box = (markup: string) => markup.match(/<span class="tnum" style="([^"]*)">/)?.[1]
    expect(box(html(45))).toBe(box(html(645)))
    expect(box(html(45))).toMatch(/width:64px/)
    expect(html(645)).toContain("10h 45m")
  })
  it("in order: −, the length, +", () => {
    const markup = html(90)
    expect(markup.indexOf("Less")).toBeLessThan(markup.indexOf("1h 30m"))
    expect(markup.indexOf("1h 30m")).toBeLessThan(markup.indexOf("More"))
  })
})
