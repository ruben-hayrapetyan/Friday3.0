// The pigments as every menu lists them (Settings → Calendars, a tag's colors, an event's paint): in the order of the
// rainbow, gray last (13 Nov, a client: "the color order is off: cobalt violet between ultramarine and magenta, gray
// last"). Black box over the paints themselves: each one's hue, around the wheel from red.
import { describe, expect, it } from "vitest"
import { PIGMENTS } from "./pigments"

/** A color's hue (0–360) and saturation (0–1) from #rrggbb. */
function hsl(hex: string): { hue: number; sat: number } {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  const l = (max + min) / 2
  const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  if (d === 0) return { hue: 0, sat }
  const hue = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  return { hue: (hue * 60 + 360) % 360, sat }
}

describe("the pigments' order", () => {
  it("goes round the rainbow from red to magenta", () => {
    const colored = PIGMENTS.filter((p) => hsl(p.light).sat > 0.2)
    const hues = colored.map((p) => hsl(p.light).hue)
    expect(hues).toEqual([...hues].sort((a, b) => a - b))
    expect(colored[0].name).toBe("Vermilion")
    expect(colored.at(-1)?.name).toBe("Magenta")
  })

  it("puts Cobalt Violet between Ultramarine and Magenta, and the gray last", () => {
    const names = PIGMENTS.map((p) => p.name)
    expect(names.indexOf("Cobalt Violet")).toBe(names.indexOf("Ultramarine") + 1)
    expect(names.indexOf("Magenta")).toBe(names.indexOf("Cobalt Violet") + 1)
    expect(PIGMENTS.at(-1)?.id).toBe("graphite")
    expect(hsl(PIGMENTS.at(-1)?.light ?? "").sat).toBeLessThan(0.2)
  })

  it("holds the same paints the server accepts", () => {
    expect(PIGMENTS.map((p) => p.id).sort()).toEqual(["blue", "graphite", "green", "orange", "pink", "purple", "red", "sapgreen", "violet", "yellow"])
  })
})
