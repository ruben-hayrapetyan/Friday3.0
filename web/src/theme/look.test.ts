import { describe, expect, it } from "vitest"
import { accentHex, oklch } from "./look"
import { PIGMENTS, pigment, WORK_PIGMENTS } from "@/lib/pigments"
import { AUTO_PAINTS, hueOf, KIND_PAINT, kindPaints, paintOf, SCHOOLWORK } from "./LookProvider"

describe("area colors", () => {
  it("reads a pigment, a stored hue, the gray, an old hex color's hue, or deals Chroma's paints by position", () => {
    expect(hueOf("green", 0)).toBe("green")
    expect(paintOf("green", false)).toBe(pigment("green", false))
    expect(hueOf("265", 0)).toBe(265)
    expect(hueOf("n", 0)).toBe("n")
    expect(hueOf(null, 2)).toBe(AUTO_PAINTS[2])
    const blue = hueOf("#3b82f6", 0) as number
    expect(blue).toBeGreaterThan(250)
    expect(blue).toBeLessThan(270)
  })

  it("paints schoolwork green and meals yellow, gives the other kinds and tags distinct paints, and keeps red", () => {
    const ids = [...PIGMENTS, ...WORK_PIGMENTS].map((p) => p.id)
    expect(new Set(AUTO_PAINTS).size).toBe(AUTO_PAINTS.length)
    expect(SCHOOLWORK.map((k) => KIND_PAINT[k])).toEqual(["green", "green", "green", "green"])
    expect(KIND_PAINT.Routine).toBe("yellow")
    // A Task wears Errand's paint (C97: both personal to-dos; no soft paint is left far from all the others)
    const rest = Object.entries(KIND_PAINT).filter(([k]) => !SCHOOLWORK.includes(k) && k !== "Task").map(([, p]) => p)
    expect(new Set(rest).size).toBe(rest.length)
    expect(rest).not.toContain("green")
    for (const paint of [...AUTO_PAINTS, ...Object.values(KIND_PAINT)]) expect(ids).toContain(paint)
    expect([...AUTO_PAINTS, ...Object.values(KIND_PAINT)]).not.toContain("red")
  })

  it("paints errands with a paint no event can wear, offered nowhere for events", () => {
    expect(KIND_PAINT.Errand).toBe("manganese")
    expect(PIGMENTS.map((p) => p.id)).not.toContain("manganese")
    expect(pigment("manganese", true)).toBe(WORK_PIGMENTS[0].light)
    expect(pigment("manganese", false)).toBe(WORK_PIGMENTS[0].dark)
  })

  it("moves a kind off a paint your events wear, to a spare one, and never two kinds onto one", () => {
    expect(kindPaints(new Set())).toEqual(KIND_PAINT)
    // The categories of 28 Oct: Ultramarine is Professional meetings, so habits move; violet and graphite are spare.
    const yours = kindPaints(new Set(["red", "blue", "sapgreen", "green", "purple", "orange", "yellow", "pink"]))
    expect(yours.Habit).not.toBe("purple")
    expect(yours["Side project"]).toBe("violet")
    expect(new Set([yours["Side project"], yours.Habit]).size).toBe(2)
    expect(yours.Assignment).toBe("green") // schoolwork stays green, meals yellow, errands Manganese Blue
    expect(yours.Routine).toBe("yellow")
    expect(yours.Errand).toBe("manganese")
    // C97, your choice (b): a Work task wears Cerulean, moved off it when your events wear it and a spare is left
    expect(KIND_PAINT["Work task"]).toBe("blue")
    const meetings = kindPaints(new Set(["blue"]))
    expect(meetings["Work task"]).not.toBe("blue")
    expect(new Set(["Side project", "Habit", "Maybe", "Work task"].map((k) => meetings[k])).size).toBe(4)
    // Every paint taken: a kind keeps its own rather than wear nothing.
    const all = kindPaints(new Set(PIGMENTS.map((p) => p.id)))
    expect(all.Habit).toBe("purple")
    for (const taken of [["violet"], ["violet", "graphite"], ["purple", "violet", "graphite"]]) {
      const moved = kindPaints(new Set(taken))
      const rest = ["Side project", "Habit", "Maybe"].map((k) => moved[k]).filter((p) => !taken.includes(p))
      expect(new Set(rest).size).toBe(rest.length)
    }
  })

  it("writes the chrome in ink: navy by default, dark on paper and light on the dark page", () => {
    expect(accentHex(255, true)).toBe(oklch(0.34, 0.075, 255))
    expect(accentHex(255, false)).toBe(oklch(0.76, 0.075, 255))
    expect(oklch(1, 0, 0)).toBe("#ffffff")
  })
})
