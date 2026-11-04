// How a block is painted (the design's `theme().skin`): by kind, in its area's colour, soft or solid, with the
// current block and the selected one ringed.

import type { Look } from "./look"

export type Kind = "planned" | "preferred" | "locked" | "tentative" | "routine" | "fixed" | "shove" | "done" | "ghost"

export interface Skin {
  bg: string
  bd: string
  fg: string
  sub: string
  stripe: string
  op: number
  shadow: string
}

const FLAT_KINDS: Kind[] = ["fixed", "routine", "shove", "ghost", "tentative", "done"]

export function skin(kind: Kind, col: string, look: Look, light: boolean, x: { isCur?: boolean; sel?: boolean } = {}): Skin {
  const mix = (p: number) => `color-mix(in srgb, ${col} ${p}%, var(--color-bg))`
  const s = base(kind, col, mix)
  if (kind === "locked") s.bd = `1px solid ${col}`
  if (!FLAT_KINDS.includes(kind) && look.blocks === "Solid") {
    Object.assign(s, { bg: col, fg: "var(--fr-ink)", sub: "color-mix(in srgb, var(--fr-ink) 72%, transparent)", stripe: "transparent" })
  }
  if (light) {
    if (s.fg === col) s.fg = `color-mix(in srgb, ${col} 50%, var(--color-text))`
    if (look.blocks !== "Solid" && (s.sub === mix(80) || s.sub === col)) s.sub = "var(--color-neutral-400)"
  }
  const glow = look.glow === "More"
  if (x.isCur) s.shadow = glow ? `0 0 0 1px ${col}, 0 0 24px 2px ${mix(55)}` : `0 0 0 2px var(--color-bg), 0 0 0 3px ${col}`
  if (x.sel) {
    s.shadow = glow
      ? "0 0 0 2px var(--color-accent), 0 0 24px color-mix(in srgb, var(--color-accent) 45%, transparent)"
      : "0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-accent)"
  }
  return s
}

function base(kind: Kind, col: string, mix: (p: number) => string): Skin {
  const s = { op: 1, shadow: "none" }
  switch (kind) {
    case "fixed":
      return { ...s, bg: "color-mix(in srgb, var(--color-text) 7%, var(--color-bg))", bd: "0", fg: "var(--color-neutral-200)", sub: "var(--color-neutral-500)", stripe: "var(--color-neutral-600)" }
    case "routine":
      return { ...s, bg: "color-mix(in srgb, var(--color-text) 3%, transparent)", bd: "0", fg: "var(--color-neutral-400)", sub: "var(--color-neutral-500)", stripe: "transparent" }
    case "shove":
      return {
        ...s,
        // Striped, as time set aside: it reads as yours at a glance, not as one more event.
        bg: "repeating-linear-gradient(135deg, color-mix(in srgb, var(--color-accent) 16%, var(--color-surface)) 0 6px, color-mix(in srgb, var(--color-accent) 8%, var(--color-surface)) 6px 12px)",
        bd: "1px dashed color-mix(in srgb, var(--color-accent) 50%, transparent)",
        fg: "var(--color-accent-200)",
        sub: "var(--color-accent-300)",
        stripe: "var(--color-accent)",
      }
    case "ghost":
      return { ...s, bg: mix(8), bd: `1px dashed ${col}`, fg: col, sub: col, op: 0.85, stripe: "transparent" }
    case "tentative":
      return { ...s, bg: "transparent", bd: `1px dashed ${mix(60)}`, fg: "var(--color-neutral-300)", sub: "var(--color-neutral-500)", stripe: "transparent" }
    case "done":
      return { ...s, bg: mix(10), bd: "0", fg: "var(--color-neutral-400)", sub: "var(--color-neutral-500)", stripe: mix(40) }
    default:
      return { ...s, bg: mix(24), bd: "0", fg: "var(--color-text)", sub: mix(80), stripe: col }
  }
}
