// personal's pigments (UI/Sources/Calendar/EventColors.swift): what an event can wear, named after real paints.
// The ids match the server's PIGMENTS; light is the paint on paper, dark the same paint lifted for the dark page.
// Meals' Ochre sits between two of them; Amber and Sap Green, its neighbours, looked like it on a block (31 Oct: clubs
// and professor office hours beside dinner), so they moved off it, to Burnt Sienna and Permanent Green (OKLab, x100:
// 12 and 13 from Ochre on paper, 10 and 12 on the dark page, where they were 8 and 10; at least 10 from every other).

export interface Pigment {
  id: string
  name: string
  light: string
  dark: string
}

export const PIGMENTS: Pigment[] = [
  { id: "red", name: "Vermilion", light: "#c2402d", dark: "#e0715f" },
  { id: "orange", name: "Burnt Sienna", light: "#d07758", dark: "#ec9c7c" },
  { id: "yellow", name: "Ochre", light: "#be9a1f", dark: "#d9b84f" },
  { id: "green", name: "Verdigris", light: "#34877a", dark: "#5fb3a5" },
  { id: "sapgreen", name: "Permanent Green", light: "#52a85b", dark: "#80d27f" },
  { id: "blue", name: "Cerulean", light: "#2a6c9c", dark: "#5f9ccb" },
  { id: "purple", name: "Ultramarine", light: "#4a48a0", dark: "#8381d6" },
  { id: "pink", name: "Magenta", light: "#a63f76", dark: "#d27aa8" },
  { id: "graphite", name: "Payne's Grey", light: "#6e7a8c", dark: "#9aa5b5" },
  { id: "violet", name: "Cobalt Violet", light: "#8a4cb5", dark: "#b689d8" },
]

// Paints only work wears, never offered for an event, so work painted with one can't be taken for an event (28 Oct:
// "errands have the same color as events"). The pigments above take every hue family, so Manganese Blue sits in the
// widest gap between them (Verdigris to Cerulean), lighter and brighter than either: further from every pigment than
// the closest two of them are from each other (OKLab), and a sky blue of its own, as a block, on paper and on the
// dark page. (Raw Umber, tried first, came out the olive of meals' yellow on the dark page.)
export const WORK_PIGMENTS: Pigment[] = [{ id: "manganese", name: "Manganese Blue", light: "#17a7d2", dark: "#19c4ec" }]

export function pigment(id: string | null | undefined, light: boolean): string | null {
  const found = PIGMENTS.find((p) => p.id === id) ?? WORK_PIGMENTS.find((p) => p.id === id)
  return found ? (light ? found.light : found.dark) : null
}

export const UNMARKED = "#8a9199" // Chroma's slate for an event no colour reached

type Painted = { color?: string | null; chroma_color?: string | null; category_color?: string | null; calendar_color?: string | null }

/** An event's paint, as Chroma chose it: its own pigment, else the one Chroma showed it in, else its category's,
 * else its calendar's, else the Unmarked slate (COMBINED.md 17). */
export function eventPaint(it: Painted, light: boolean): string {
  return pigment(it.color, light) ?? pigment(it.chroma_color, light) ?? pigment(it.category_color, light) ?? pigment(it.calendar_color, light) ?? UNMARKED
}

/** Chroma's wash: the paint at 11% over the page (a little more on the dark page, where 11% vanishes). */
export const wash = (paint: string, light: boolean) => `color-mix(in srgb, ${paint} ${light ? 11 : 16}%, var(--color-surface))`
