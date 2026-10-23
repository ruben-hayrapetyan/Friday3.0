// personal's pigments (UI/Sources/Calendar/EventColors.swift): what an event can wear, named after real paints.
// The ids match the server's PIGMENTS; light is the paint on paper, dark the same paint lifted for the dark page.

export interface Pigment {
  id: string
  name: string
  light: string
  dark: string
}

export const PIGMENTS: Pigment[] = [
  { id: "red", name: "Vermilion", light: "#c2402d", dark: "#e0715f" },
  { id: "orange", name: "Amber", light: "#ce7c22", dark: "#e39a4f" },
  { id: "yellow", name: "Ochre", light: "#be9a1f", dark: "#d9b84f" },
  { id: "green", name: "Verdigris", light: "#34877a", dark: "#5fb3a5" },
  { id: "sapgreen", name: "Sap Green", light: "#74a03a", dark: "#97c463" },
  { id: "blue", name: "Cerulean", light: "#2a6c9c", dark: "#5f9ccb" },
  { id: "purple", name: "Ultramarine", light: "#4a48a0", dark: "#8381d6" },
  { id: "pink", name: "Magenta", light: "#a63f76", dark: "#d27aa8" },
  { id: "graphite", name: "Payne's Grey", light: "#6e7a8c", dark: "#9aa5b5" },
  { id: "violet", name: "Cobalt Violet", light: "#8a4cb5", dark: "#b689d8" },
]

export function pigment(id: string | null | undefined, light: boolean): string | null {
  const found = PIGMENTS.find((p) => p.id === id)
  return found ? (light ? found.light : found.dark) : null
}
