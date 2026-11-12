// How a block is painted (skin.ts): by kind, in its tag's colour, soft or solid, with the block going on now and the
// selected one ringed, the ring glowing when the glow is up.
import { describe, expect, it } from "vitest"
import { DEFAULT_LOOK, type Look } from "./look"
import { type Kind, skin } from "./skin"

const COL = "#2a6c9c"
const look = (over: Partial<Look> = {}): Look => ({ ...DEFAULT_LOOK, ...over })
const mix = (p: number) => `color-mix(in srgb, ${COL} ${p}%, var(--color-bg))`

describe("a block's paint", () => {
  it("is a soft wash of its colour with a stripe, for planned work", () => {
    const s = skin("planned", COL, look(), false)
    expect(s).toEqual({ bg: mix(24), bd: "0", fg: "var(--color-text)", sub: mix(80), stripe: COL, op: 1, shadow: "none" })
  })

  it("is filled with its colour when blocks are solid, and the words are written in the page's ink", () => {
    const s = skin("preferred", COL, look({ blocks: "Solid" }), false)
    expect(s).toMatchObject({ bg: COL, fg: "var(--fr-ink)", stripe: "transparent" })
    expect(s.sub).toBe("color-mix(in srgb, var(--fr-ink) 72%, transparent)")
  })

  it("keeps the flat kinds flat however blocks are drawn", () => {
    for (const kind of ["fixed", "routine", "shove", "ghost", "tentative", "done"] as Kind[]) {
      expect(skin(kind, COL, look({ blocks: "Solid" }), false)).toEqual(skin(kind, COL, look(), false))
    }
  })

  it("draws each kind as itself: events grey, routines faint, Shove striped, a ghost dashed and see-through", () => {
    expect(skin("fixed", COL, look(), false).stripe).toBe("var(--color-neutral-600)")
    expect(skin("routine", COL, look(), false)).toMatchObject({ fg: "var(--color-neutral-400)", stripe: "transparent" })
    const shove = skin("shove", COL, look(), false)
    expect(shove.bg).toMatch(/^repeating-linear-gradient\(135deg/)
    expect(shove.bd).toContain("dashed")
    const ghost = skin("ghost", COL, look(), false)
    expect(ghost).toMatchObject({ bg: mix(8), bd: `1px dashed ${COL}`, fg: COL, op: 0.85 })
    expect(skin("tentative", COL, look(), false).bd).toBe(`1px dashed ${mix(60)}`)
    expect(skin("done", COL, look(), false)).toMatchObject({ bg: mix(10), stripe: mix(40) })
  })

  it("edges a locked block in its colour", () => {
    expect(skin("locked", COL, look(), false).bd).toBe(`1px solid ${COL}`)
  })

  it("on paper, softens a colour used for words, and greys the small line", () => {
    expect(skin("ghost", COL, look(), true).fg).toBe(`color-mix(in srgb, ${COL} 50%, var(--color-text))`)
    expect(skin("planned", COL, look(), true).sub).toBe("var(--color-neutral-400)")
    // solid blocks keep their own small line on paper
    expect(skin("planned", COL, look({ blocks: "Solid" }), true).sub).toBe("color-mix(in srgb, var(--fr-ink) 72%, transparent)")
  })

  it("rings the block going on now in its colour, and the selected one in the accent", () => {
    expect(skin("planned", COL, look(), false, { isCur: true }).shadow).toBe(`0 0 0 2px var(--color-bg), 0 0 0 3px ${COL}`)
    expect(skin("planned", COL, look(), false, { sel: true }).shadow).toBe("0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-accent)")
    // selected wins over now
    expect(skin("planned", COL, look(), false, { isCur: true, sel: true }).shadow).toContain("var(--color-accent)")
  })

  it("lets those rings glow when the glow is up", () => {
    expect(skin("planned", COL, look({ glow: "More" }), false, { isCur: true }).shadow).toBe(`0 0 0 1px ${COL}, 0 0 24px 2px ${mix(55)}`)
    expect(skin("planned", COL, look({ glow: "More" }), false, { sel: true }).shadow).toContain("0 0 24px color-mix(in srgb, var(--color-accent) 45%, transparent)")
  })
})
