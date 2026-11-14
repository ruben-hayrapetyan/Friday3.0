// The walk's and the tour's numbers in VT323, a pixel font whose 5 and 2 can't be taken for an 8 (13 Nov: clients read
// Pixelify Sans's "6:15am" as "6:18am" and "12am" as "18am"; of six fonts shown, you picked VT323). The time cards and
// big numbers use it outright (setup.css --wk-digits); digits inside the pixel font's words and titles take it too,
// through "Walk Digits": VT323 for 0–9 and the colon only, sized to sit beside Pixelify's letters, and first in
// --wk-pixel and --gd-pixel.
import "@fontsource/vt323/400.css"
import vt323 from "@fontsource/vt323/files/vt323-latin-400-normal.woff2?url"

export const WALK_DIGITS = "Walk Digits"
export const DIGITS_RANGE = "U+0030-003A" // 0–9 and :
export const DIGITS_SIZE = "122%" // VT323 draws small: this matches Pixelify's digits in height

type Fonts = { add: (face: FontFace) => unknown; check?: (font: string) => boolean }
type Make = (family: string, source: string, descriptors: FontFaceDescriptors & { sizeAdjust?: string }) => FontFace

/** Registers "Walk Digits" once (a page without the FontFace API, as in tests, goes without: the pixel font shows). */
export function addWalkDigits(
  fonts: Fonts | undefined = typeof document !== "undefined" ? (document.fonts as unknown as Fonts) : undefined,
  make: Make | undefined = typeof FontFace !== "undefined" ? (family, source, descriptors) => new FontFace(family, source, descriptors) : undefined,
): FontFace | null {
  if (!fonts || !make || added) return added
  added = make(WALK_DIGITS, `url(${vt323}) format("woff2")`, { unicodeRange: DIGITS_RANGE, sizeAdjust: DIGITS_SIZE, display: "block" })
  fonts.add(added)
  return added
}
let added: FontFace | null = null

/** For tests: forget the registered face. */
export const resetWalkDigits = () => {
  added = null
}

addWalkDigits()
