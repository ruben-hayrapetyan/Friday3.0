// The look in effect, for every component: change it from Settings, read area colours anywhere.

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react"
import { useAreas } from "@/hooks/queries"
import { PIGMENTS, pigment } from "@/lib/pigments"
import { applyLook, areaHex, isLight, loadLook, type Look, saveLook } from "./look"
import { type Kind, type Skin, skin } from "./skin"

interface LookContext {
  look: Look
  light: boolean
  setLook: (change: Partial<Look> | null) => void // null resets to the default
  color: (area: string | null | undefined, preset?: string | null) => string
  skinOf: (kind: Kind, area: string | null | undefined, x?: { isCur?: boolean; sel?: boolean }, preset?: string | null) => Skin
}

const Ctx = createContext<LookContext | null>(null)

export function LookProvider({ children }: { children: ReactNode }) {
  const [look, setState] = useState(loadLook)
  const [light, setLight] = useState(() => isLight(look))
  useEffect(() => {
    applyLook(look)
    setLight(isLight(look))
    if (look.theme !== "Match system") return
    const media = matchMedia("(prefers-color-scheme: light)")
    const follow = () => {
      applyLook(look)
      setLight(isLight(look))
    }
    media.addEventListener("change", follow)
    return () => media.removeEventListener("change", follow)
  }, [look])
  const setLook = useCallback((change: Partial<Look> | null) => {
    setState((old) => {
      const next = change === null ? loadDefault() : { ...old, ...change }
      saveLook(next)
      return next
    })
  }, [])
  const hues = useAreaHues()
  const value = useMemo<LookContext>(() => {
    // A tag's own paint, else (work with no tag) its kind's, else the neutral grey of meals and routines.
    const color = (area: string | null | undefined, preset?: string | null) => {
      const tagged = area ? hues.get(area) : undefined
      if (tagged !== undefined) return paintOf(tagged, light)
      return pigment(preset ? KIND_PAINT[preset] : null, light) ?? areaHex("n", light)
    }
    // Work with neither a tag nor a kind with a paint wears the ink Friday writes in, not grey.
    const paint = (kind: Kind, area: string | null | undefined, preset?: string | null) =>
      area || kind === "routine" || kind === "fixed" || (preset && KIND_PAINT[preset]) ? color(area, preset) : "var(--color-accent)"
    return { look, light, setLook, color, skinOf: (kind, area, x, preset) => skin(kind, paint(kind, area, preset), look, light, x) }
  }, [look, light, setLook, hues])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

function loadDefault(): Look {
  localStorage.removeItem("friday-look-v8")
  return loadLook()
}

export function useLook(): LookContext {
  const value = useContext(Ctx)
  if (!value) throw new Error("useLook outside LookProvider")
  return value
}

// Chroma's paints, in the order tags are dealt them: each far from the one before, so neighbours never look alike.
// Vermilion is left out: red is kept for now and overdue.
export const AUTO_PAINTS = ["blue", "orange", "green", "violet", "yellow", "pink", "sapgreen", "purple", "graphite"]
// Work with no tag wears its kind's paint (soft, as an event's): everything towards finishing schoolwork is one green,
// meals are yellow, and the rest each have a paint of their own.
export const SCHOOLWORK = ["Assignment", "Reading", "Exam prep", "Project"]
export const KIND_PAINT: Record<string, string> = {
  ...Object.fromEntries(SCHOOLWORK.map((kind) => [kind, "green"])),
  Routine: "yellow",
  Errand: "pink",
  "Side project": "violet",
  Habit: "purple",
  Maybe: "graphite",
}
// Kept for older tags given a hue: the swatches now offer Chroma's paints.
export const AUTO_HUES = [265, 60, 155, 0, 290, 200, 30, 120, 330, 230, 90, 180]

type Paint = number | "n" | string // a hue, the neutral grey, or a pigment's id

/** Each tag's paint: a pigment it was given, a hue (a number, or "n" for grey), an old hex colour's hue, or the next
 * of Chroma's paints in the order the tags were made. */
function useAreaHues(): Map<string, Paint> {
  const areas = useAreas().data ?? []
  return useMemo(() => new Map(areas.map((a, i) => [a.name, hueOf(a.color, i)])), [areas])
}

export function hueOf(color: string | null | undefined, index: number): Paint {
  if (color === "n") return "n"
  if (color && PIGMENTS.some((p) => p.id === color)) return color
  if (color && /^\d{1,3}$/.test(color)) return Number(color) % 360
  if (color && /^#[0-9a-f]{6}$/i.test(color)) return hexHue(color)
  return AUTO_PAINTS[index % AUTO_PAINTS.length]
}

/** A paint as a colour: a pigment's, else a hue's. */
export function paintOf(paint: Paint, light: boolean): string {
  return typeof paint === "string" && paint !== "n" ? (pigment(paint, light) ?? areaHex("n", light)) : areaHex(paint as number | "n", light)
}

/** The OKLCH hue of a hex colour. */
function hexHue(hex: string): number {
  const lin = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  const [r, g, b] = lin
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  return Math.round(((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360)
}
